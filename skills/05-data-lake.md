---
type: skill
category: data-lake
priority: 5
keywords: [HMS, Hive, Kerberos, HDFS, S3, external table, data lake, catalog]
---

# 05 - Data Lake / External Table Troubleshooting

Investigation guide for Hive Metastore connectivity, Kerberos authentication, HDFS/S3
access errors, and external catalog query failures.

---

## 1. Hive Metastore Connection Issues

| Error keyword | Investigation direction |
|---|---|
| `set_ugi() not successful` | Check Kerberos config; verify `HADOOP_USER_NAME` in `hadoop_env.sh` |
| `GSS initiate failed` | Verify keytab is not expired (`klist`); check JCE extensions |
| `Failed to get current notification event id` | Check HMS user permissions; configure `HADOOP_USER_NAME` |
| `Filesystem closed` | Increase `hdfs_client_max_cache_size` (must exceed total namenode count) |

---

## 2. Kerberos Debugging

Enable Kerberos debug logging in FE/BE config:

```
# In fe.conf JAVA_OPTS:
-Dsun.security.krb5.debug=true

# In be/conf/hadoop_env.sh:
HADOOP_OPTS="$HADOOP_OPTS -Dsun.security.krb5.debug=true"
```

Debug output goes to `fe.out` / `be.out`.

---

## 3. S3 / Object Storage Issues

- EC2 instances can use IAM Roles without AK/SK, but must not set `AWS_EC2_METADATA_DISABLED`.
- Non-EC2 environments require AK/SK/Endpoint configuration.
- Connection pool exhaustion: increase `fs.s3a.connection.maximum` (for Paimon Catalog use `paimon.option.fs.s3a.connection.maximum`).

### SSL Issues with Private OSS

Some private object-storage deployments do not support SSL. StarRocks defaults to SSL-encrypted
access; if `ssl_enable` is required to be off, ensure you are on a version where the parameter
takes effect (older releases had a bug ignoring the flag).

---

## 4. Network-Layer Bottlenecks

When external-table queries saturate a CN/BE node's network bandwidth, the HMS service may be
the upstream cause. Symptoms:

- Continuous network saturation on a single node.
- jstack shows threads blocked on `org.apache.hadoop.hive.metastore.security.TFilterTransport.readAll`.
- Heavy JOINs between internal tables and external (Hive/Iceberg) tables generate large shuffles.

Mitigation:

- Add timeout controls for HMS access.
- Investigate HMS service health independently.
- Reduce external-table JOIN cardinality with predicate pushdown and partition pruning.

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `GSS initiate failed` | Expired keytab or missing JCE | Renew keytab; install JCE extensions |
| `Filesystem closed` | NN cache too small | Increase `hdfs_client_max_cache_size` |
| `503 reduce request rate` from S3 | S3 rate limit | Use `num_partitioned_prefix`; see `skills/06-shared-data.md` |
| External JOIN saturates network | HMS slow + large shuffle | Fix HMS; reduce shuffle |
| SSL handshake error to private OSS | Default SSL on; param bug | Upgrade to fixed version; disable SSL param |

---

## Related Cases

- `case-005-ssl-certificate` — private OSS SSL issue blocking Broker Load
- `case-006-network-saturation` — HMS degradation saturating CN network

---

## Resources

- [Hive catalog documentation](https://docs.starrocks.io/docs/data_source/catalog/hive_catalog/)
