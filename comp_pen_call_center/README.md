## Running

- Make sure the call center data is either named `data.xls` or has been overridden in the compose file (DATA_FILE environment variable.).
- Then, from this directory:
- `docker compose up`
- Open http://localhost:5601
- Go to "Management/Stack Management"
- From the "Stack Management" screen, select "Kibana/Saved Objects"
- From the "Saved Objects" screen select "Import" and find `export.ndjson` in the same directory as the `compose.yml`.
- There's a link for 'Notifications', which takes you to Discover, or open the hamburger menu and go to "Analytics/Discover".
- You should now see a search view of the comp and pen call center data, with search filters and appropriate time range.