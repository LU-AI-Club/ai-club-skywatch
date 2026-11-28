-- SkyWatch — demo data for the detections console (/cases) and its per-case map.
--
-- NOT loaded automatically (only db/schema/* runs on first boot). Run it by hand
-- against a running database to make the console show something:
--
--   docker compose exec -T db psql -U skywatch -d skywatch < db/samples/console_demo.sql
--
-- It inserts a handful of sample ADS-B tracks into `observations` and one
-- detection per detector that references them, all near Lynchburg and timestamped
-- "now", so they fall inside the console's 24h window and the live map's 1h
-- window. Re-running it first removes the previous demo rows, so it is safe to
-- run repeatedly. To remove the demo data entirely:
--
--   DELETE FROM observations WHERE source_id = 'sample';
--   DELETE FROM spoofing_detections     WHERE dedup_key LIKE 'sample-%';
--   DELETE FROM proximity_detections    WHERE dedup_key LIKE 'sample-%';
--   DELETE FROM no_fly_zone_detections  WHERE dedup_key LIKE 'sample-%';

BEGIN;

-- 1. Clean out any previous run so this is idempotent.
DELETE FROM observations          WHERE source_id = 'sample';
DELETE FROM spoofing_detections   WHERE dedup_key LIKE 'sample-%';
DELETE FROM proximity_detections  WHERE dedup_key LIKE 'sample-%';
DELETE FROM no_fly_zone_detections WHERE dedup_key LIKE 'sample-%';

-- 2. Sample aircraft tracks. Each aircraft gets 8 fixes, one per minute over the
--    last 7 minutes, as a straight line. h3 indexes aren't used by the API, so 0
--    is fine for demo rows.
--    Columns: i=0..7 walks the track; lat/lon = start + i*delta.
INSERT INTO observations
    (observed_at, entity_id, domain, source_id, location,
     h3_index_res7, h3_index_res9, sog, cog, heading, payload, provenance_id, raw_record_ref)
SELECT
    now() - make_interval(mins => (7 - i)),
    a.entity_id, 'air', 'sample',
    ST_SetSRID(ST_MakePoint(a.lon0 + i * a.dlon, a.lat0 + i * a.dlat), 4326)::geography,
    0, 0, a.sog, a.cog, a.cog,
    a.payload::jsonb,
    gen_random_uuid(),
    'sample:' || a.entity_id || ':' || i
FROM generate_series(0, 7) AS i
CROSS JOIN (VALUES
    -- entity_id,         lat0,    lon0,    dlat,      dlon,      sog, cog, payload
    ('icao24:aa1001', 37.250, -79.300,  0.021430,  0.028570, 430, 45,
        '{"callsign":"SPOOF1","altitude_ft":"33000","squawk":"1200","emitter_category":"A3"}'),
    ('icao24:bb2001', 37.300, -79.350,  0.004710,  0.023570, 300, 80,
        '{"callsign":"PROX1","altitude_ft":"10000","squawk":"4471","emitter_category":"A3"}'),
    ('icao24:bb2002', 37.370, -79.350, -0.004860,  0.022860, 280, 100,
        '{"callsign":"PROX2","altitude_ft":"10200","squawk":"5213","emitter_category":"A1"}'),
    ('icao24:cc3001', 37.460, -79.280, -0.007140,  0.017140, 190, 120,
        '{"callsign":"NFZ1","altitude_ft":"4500","squawk":"7001","emitter_category":"A5"}')
) AS a(entity_id, lat0, lon0, dlat, dlon, sog, cog, payload);

-- 3a. Spoofing: one aircraft, a kinematic inconsistency at its latest fix.
INSERT INTO spoofing_detections
    (detection_id, dedup_key, detector_id, detector_version, detection_type,
     severity, confidence, entity_id, entities_involved,
     temporal_bounds_start, temporal_bounds_end, latitude, longitude,
     evidence, geospatial_context, provenance, tags, metadata, raw_detection,
     detection_run_id, first_detected_at, last_detected_at, created_at)
VALUES (
    gen_random_uuid(), 'sample-spoof-aa1001', 'skywatch.spoofing', '0.1.0',
    'kinematic_inconsistency', 'high', 0.86,
    'aircraft:aa1001', '[{"domain":"air","entity_id":"aircraft:aa1001","entity_type":"aircraft"}]',
    now() - make_interval(mins => 7), now(), 37.400, -79.100,
    '[{"summary":"aa1001: reported 430 kt but implied ground speed 512 kt","evidence_type":"kinematic_pair"}]',
    '{}', '{}', '[]',
    '{"gate":"speed_delta_v1","reason":"SPEED_DISAGREEMENT","measured":512.0,"threshold":480.0,"anomaly_score":0.71,"explanation_facts":["Gate speed_delta_v1: the implied ground speed between two fixes disagrees with the reported speed."],"limitations":["Reports a deviation only; intent is not assessed."]}',
    '{}', NULL, now() - make_interval(mins => 7), now(), now());

-- 3b. Proximity: a converging PAIR, predicted closest approach 0.4 nm / 300 ft.
INSERT INTO proximity_detections
    (detection_id, dedup_key, detector_id, detector_version, detection_type,
     severity, confidence, entity_id, entities_involved,
     temporal_bounds_start, temporal_bounds_end, latitude, longitude,
     evidence, geospatial_context, provenance, tags, metadata, raw_detection,
     detection_run_id, first_detected_at, last_detected_at, created_at,
     member_entity_ids, predicted_horizontal_nm, predicted_vertical_ft, t_cpa_seconds)
VALUES (
    gen_random_uuid(), 'sample-prox-bb2001-bb2002', 'skywatch.proximity', '0.1.0',
    'predicted_proximity', 'critical', 0.92,
    'aircraft:bb2001', '[{"entity_id":"aircraft:bb2001"},{"entity_id":"aircraft:bb2002"}]',
    now() - make_interval(mins => 5), now(), 37.333, -79.190,
    '[{"summary":"bb2001 and bb2002 predicted within 0.4 nm / 300 ft in 45 s","evidence_type":"cpa"}]',
    '{}', '{}', '[]',
    '{"reason":"PREDICTED_PROXIMITY","explanation_facts":["Two aircraft are predicted to pass within 0.4 nm horizontally and 300 ft vertically about 45 s from now."]}',
    '{}', NULL, now() - make_interval(mins => 5), now(), now(),
    ARRAY['aircraft:bb2001','aircraft:bb2002'], 0.4, 300, 45);

-- 3c. No-fly zone: one aircraft inside a restricted area for ~3 minutes.
INSERT INTO no_fly_zone_detections
    (detection_id, dedup_key, detector_id, detector_version, detection_type,
     severity, confidence, entity_id, entities_involved,
     temporal_bounds_start, temporal_bounds_end, latitude, longitude,
     evidence, geospatial_context, provenance, tags, metadata, raw_detection,
     detection_run_id, first_detected_at, last_detected_at, created_at,
     zone_id, zone_name, zone_type)
VALUES (
    gen_random_uuid(), 'sample-nfz-cc3001', 'skywatch.no_fly_zone', '0.1.0',
    'restricted_airspace_incursion', 'high', 0.88,
    'aircraft:cc3001', '[{"entity_id":"aircraft:cc3001"}]',
    now() - make_interval(mins => 3), now(), 37.410, -79.160,
    '[{"summary":"cc3001 entered restricted airspace DEMO-R1","evidence_type":"zone_incursion"}]',
    '{}', '{}', '[]',
    '{"reason":"ZONE_INCURSION","explanation_facts":["Aircraft crossed into restricted airspace and remained inside for about 3 minutes."]}',
    '{}', NULL, now() - make_interval(mins => 3), now(), now(),
    'DEMO-R1', 'Demo Restricted Area', 'RESTRICTED');

COMMIT;

-- Quick confirmation.
SELECT 'observations (sample)' AS what, count(*) FROM observations WHERE source_id = 'sample'
UNION ALL SELECT 'spoofing',    count(*) FROM spoofing_detections    WHERE dedup_key LIKE 'sample-%'
UNION ALL SELECT 'proximity',   count(*) FROM proximity_detections   WHERE dedup_key LIKE 'sample-%'
UNION ALL SELECT 'no_fly_zone', count(*) FROM no_fly_zone_detections WHERE dedup_key LIKE 'sample-%';
