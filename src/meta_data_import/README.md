# XBLIG metadata import

Files:

- `xblig_metadata.sql` - creates the reference catalogue table.
- `import_xblig_metadata.py` - imports the `XBLIG Games` sheet using openpyxl.

Usage:

```powershell
python import_xblig_metadata.py path\to\database.db "List of Xbox Live Indie Games.xlsx"
```

The importer is idempotent: re-running it updates existing rows based on
`normalized_title` instead of creating duplicates.

The catalogue is deliberately separate from the main `games` table. This
keeps the historical XBLIG dataset intact and lets the application use it as
metadata/enrichment data.

The spreadsheet does not contain a dedicated publisher field. For XBLIG,
`developer` and `developer_account` are retained separately so the application
can decide how to populate `XBLIGGame.publisher`.
