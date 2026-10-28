# Unknown observation clocks — proposed additive onboarding migration

Status: **Deferred for concentration facts**. No production concentration-clock migration applied.
The current `fact_air_quality_hourly.observed_at_utc` is NOT NULL; the provenance
sidecar deliberately permits NULL. API Ninjas pure adapter preserves an unknown
actual observation time. It cannot yet be written through the concentration
province adapter. Provider-reported AQI is now published separately through the
AQI facts with nullable source clocks and `aqi_origin=provider`; that path does
not claim a concentration observation interval or enable computed VN_AQI.
`verify_storage_clock` rejects that case before writes; collection or scheduled
time never supplies a fabricated observation clock. Hourly means with a verified
interval-end observation clock are supported and preserve that clock separately
from `hour_start_utc` (verified in the 31-day benchmark).

## Migration contract `observation-clock-v2` (not activated)

1. Require a reviewed source/location/unit contract and succeeded Silver runs.
   Define whether a snapshot hour is a scheduled label, collection bucket or a
   real measurement interval. Never infer an interval or mean from cadence.
2. Add nullable `source_record_present BOOLEAN` and `observation_time_kind STRING`
   to the fact and serving marts. Old immutable releases retain their schema;
   readers interpret an old fact as a present record and use existing provenance
   when available. New serving spines set record presence false only for absent
   observations, even when all observations of one expected pollutant are absent.
3. Validate readers and quality calculations against record presence before
   relaxing the fact's observation timestamp constraint. Today `observed_slots`
   is a count of known observation clocks, equal to record presence for admitted
   sources. Simply dropping NOT NULL would undercount snapshots and can produce
   a negative `missing_value_slots = observed_slots - valid - invalid`.
4. Apply Iceberg additive columns and then `ALTER COLUMN observed_at_utc DROP
   NOT NULL` only on the reviewed onboarding scope. Record migration/source
   contract hashes, build fresh releases and publish a distinct compatibility
   lane. Preserve all old release snapshot mappings. Do not rewrite old snapshots.
5. Validate known/unknown clocks, valid/invalid/absent records, provider AQI,
   native 3h and 1h instantaneous, true 1h means, source quality and dashboard
   freshness. Unknown-clock snapshots remain temporally ineligible for VN_AQI.
   Expose clock kind and NULL observation time in API; label collection freshness
   separately. No station/city proxy is promoted to province representativeness.

Rollback restores the old immutable historical view and disables the new source
contract. Additive columns remain; do not restore NOT NULL while retained new
releases contain unknown clocks. Snapshot expiration is not part of this plan.

The existing hourly architecture needs no cadence migration. Implementing this
conditional migration now would publish an untested production source path with
no succeeded upstream data; it is deliberately gated until that input exists.
