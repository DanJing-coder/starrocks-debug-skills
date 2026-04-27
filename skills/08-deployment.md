---
type: skill
category: deployment
priority: 8
keywords: [FE startup, BE startup, port conflict, BDB, JDK, priority_networks, helper, NTP]
---

# 08 - Deployment Troubleshooting

Investigation guide for FE and BE startup failures, port conflicts, BDB residual entries,
JDK/JRE issues, and priority network configuration.

---

## 1. FE Startup Issues

| Symptom | Log Keyword | Fix |
|---|---|---|
| FE process not found | `port xxx is used` | Change port in `fe.conf`, restart |
| FE process not found | `meta not exist` | Create meta directory under FE install path |
| FE process not found | `Could not initialize class...BackendServiceProxy` | Use JDK (not JRE), Oracle JDK 1.8+ |
| FE alive=false | `Fe type:unknown, is ready:false` + `current node is not added` | Run `ALTER SYSTEM ADD FOLLOWER/OBSERVER "host:port"` first |
| FE alive=false | `backend ip saved in master does not equal to backend local ip` | Configure `priority_networks` in `fe.conf` |
| FE alive=false | `this replica exceeds max permissible delta:5000ms` | Sync server clocks (NTP), max allowed delta is 5s |
| FE alive=false | `connection refused` | Check network connectivity between FE nodes on `http_port` |
| FE shows false on other FEs | Follower started without `--helper` | Clear meta, restart with `--helper host:port` |
| FE shows false, large BDB | BDB folder growing, no checkpoint | Increase FE JVM heap in `JAVA_OPTS`, restart |
| BDB conflict | `It conflicts with the socket already used by the member` | Use `DbGroupAdmin -removeMember` to clean residual entries |

---

## 2. BE Startup Issues

| Symptom | Log Keyword | Fix |
|---|---|---|
| BE process not found | `port xxx is used` | Change port in `be.conf` |
| BE process not found | `storage not exist` | Create storage directory |
| BE process not found | `Be http service did not start correctly` | Change webserver port, check for YARN port conflicts |
| BE process not found | `Could not initialize class...BackendServiceProxy` | Use JDK, not JRE |
| BE process not found | `load tablet from header failed` | Use `meta_tool` to clean corrupted tablet |
| BE not visible | `show backends` empty | `ALTER SYSTEM ADD BACKEND "host:port"` (heartbeat_service_port, default 9050) |
| BE unavailable | `Failed to get scan range, no queryable replica found` | Disk full — add storage paths in `be.conf` `storage_root_path` |

---

## 3. Multi-NIC and Priority Networks

When FE/BE hosts have multiple NICs, configure `priority_networks` in both `fe.conf` and `be.conf`
to lock the IP used for cluster communication. Without it, the wrong NIC can be picked, leading
to `backend ip saved in master does not equal to backend local ip`.

---

## 4. JDK / JRE

Always install the JDK, not just the JRE — the FE startup process requires `tools.jar`.
Oracle JDK 1.8+ is recommended.

---

## 5. SSL Errors During Imports

If Broker Load (or other ingest paths) fail with SSL handshake errors when targeting private
or self-managed object storage, check whether the cluster has a working `ssl_enable` flag.
See `case-005-ssl-certificate` for context.

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `port xxx is used` at startup | Port collision with YARN, NodeManager, etc. | Change port; verify with `ss -lntp` |
| FE follower stuck `is ready:false` | Started without `--helper` | Clear meta, restart with `--helper` |
| Replica delta exceeded | Clock drift across hosts | Configure NTP |
| BDB conflict on rejoin | Residual member not removed | `DbGroupAdmin -removeMember` |
| BE shown with old IP | Multi-NIC, no priority_networks | Set `priority_networks` |

---

## Related Cases

- `case-005-ssl-certificate` — SSL handshake error against private object storage during Broker Load

---

## Resources

- [Operation & Maintenance FAQ](https://docs.starrocks.io/docs/faq/operation_maintenance_faq)
