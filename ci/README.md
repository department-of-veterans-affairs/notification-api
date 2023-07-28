### Testing Write and Read instance

- change docker file to enable read instance
- 

#### copy write database
```
pg_dump -U postgres -W -F t notification_api > /var/db-data/writedb.dump
```

#### restore data from write instance on read instance
```
pg_restore -U postgres -W -d notification_api /var/db-data-read/writedb.dump
```

