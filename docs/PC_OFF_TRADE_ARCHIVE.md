# PC-off trade archive

The public site uses `data/public/shards/manifest.json`, never a count-only
`local_meta.json`, for its available-history total. `trade_count` is the sum of
monthly history counts; `detail_trade_count` is the number of downloadable
individual transactions. The two may differ where only monthly history exists.

## Persistence and daily updates

- District history is gzip JSON. Individual records are split into 16 stable
  SHA-256 buckets per district, selected by `dong + NUL + official apartment name`.
  The browser loads only the selected apartment's bucket. No PC service or R2
  account is required.
- `Daily real-estate update` runs on GitHub Actions daily at 21:05 UTC
  (06:05 Korea; GitHub may delay scheduled starts). It refreshes the latest two
  months, or three months on the first day of a month, with failed-request retries.
- Only successfully collected non-empty district/months replace old records.
  Failed/empty responses retain previous data. Identical-looking official sales
  are not collapsed. Old periods remain in the repository across runs.
- The trade pipeline tests, per-file SHA-256 and counts, aggregate loss guard,
  and file/site size checks gate publication. Unrelated news/editorial checks run
  separately in application CI and cannot block a valid transaction update.
- `collection_status.json` reports the most recent collector run; file-level
  verification is in `archive_verification.json`. GitHub Pages deploys after the
  daily workflow completes, including a partial run whose good data was saved.

## Rebuilding from a PC database

Run `python scripts/public_trade_archive.py seed --database <SQLite path>` from
the checkout. The database is opened read-only in a stable transaction. Published
months not covered by the PC remain available; complete historical district/month
partitions prevent API/CSV area-rounding aliases from double-counting transactions.
Review and run `python scripts/public_trade_archive.py validate` before committing
the archive. Never replace it with the legacy `build_public_trade_shards.py`
output, which is based on an older, limited monolithic history snapshot.

This is not a claim that all national historical transactions have been collected:
district coverage and the locally collected historical range remain incomplete.
There is no 1-million-row GitHub limit. The exporter enforces a 50 MiB per-file
budget and an 850 MiB public-data budget to leave space within the Pages site limit.
