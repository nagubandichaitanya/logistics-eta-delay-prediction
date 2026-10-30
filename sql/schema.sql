-- Logistics ETA project: PostgreSQL schema
-- Run: psql -U postgres -d logistics_eta -f sql/schema.sql
CREATE TABLE IF NOT EXISTS carrier (
  carrier_id TEXT PRIMARY KEY,
  carrier_name TEXT NOT NULL CHECK (length(trim(carrier_name)) > 0),
  carrier_type TEXT NOT NULL CHECK (carrier_type IN ('ROAD','AIR','RAIL','OCEAN','MULTIMODAL')),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facility (
  facility_id TEXT PRIMARY KEY,
  facility_name TEXT NOT NULL,
  facility_type TEXT NOT NULL CHECK (facility_type IN ('ORIGIN','HUB','WAREHOUSE','PORT','DESTINATION')),
  city TEXT NOT NULL, state TEXT NOT NULL, country TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  capacity_per_hour INTEGER NOT NULL CHECK (capacity_per_hour > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_level (
  service_level_id TEXT PRIMARY KEY,
  service_name TEXT NOT NULL,
  target_hours NUMERIC(8,2) NOT NULL CHECK (target_hours > 0),
  late_grace_minutes INTEGER NOT NULL DEFAULT 0 CHECK (late_grace_minutes >= 0),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS route (
  route_id TEXT PRIMARY KEY,
  origin_facility_id TEXT NOT NULL REFERENCES facility(facility_id),
  destination_facility_id TEXT NOT NULL REFERENCES facility(facility_id),
  distance_km NUMERIC(10,2) NOT NULL CHECK (distance_km > 0),
  transport_mode TEXT NOT NULL CHECK (transport_mode IN ('ROAD','AIR','RAIL','OCEAN')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (origin_facility_id <> destination_facility_id)
);

CREATE TABLE IF NOT EXISTS shipment (
  shipment_id TEXT PRIMARY KEY,
  service_level_id TEXT NOT NULL REFERENCES service_level(service_level_id),
  origin_facility_id TEXT NOT NULL REFERENCES facility(facility_id),
  destination_facility_id TEXT NOT NULL REFERENCES facility(facility_id),
  created_at TIMESTAMPTZ NOT NULL,
  planned_pickup_at TIMESTAMPTZ NOT NULL,
  promised_delivery_at TIMESTAMPTZ NOT NULL,
  actual_delivery_at TIMESTAMPTZ,
  current_status TEXT NOT NULL CHECK (current_status IN
    ('CREATED','PICKED_UP','IN_TRANSIT','AT_FACILITY','OUT_FOR_DELIVERY','DELIVERED','EXCEPTION','CANCELLED')),
  priority TEXT NOT NULL CHECK (priority IN ('LOW','STANDARD','HIGH','CRITICAL')),
  weight_kg NUMERIC(10,3) NOT NULL CHECK (weight_kg > 0),
  CHECK (created_at <= planned_pickup_at),
  CHECK (planned_pickup_at <= promised_delivery_at),
  CHECK (actual_delivery_at IS NULL OR actual_delivery_at >= planned_pickup_at)
  -- Deliberate status-vs-delivery inconsistencies must remain representable
  -- so validation can flag and ground-truth can label the negative scenario.
);

CREATE TABLE IF NOT EXISTS shipment_leg (
  leg_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  leg_sequence INTEGER NOT NULL CHECK (leg_sequence >= 1),
  route_id TEXT NOT NULL REFERENCES route(route_id),
  carrier_id TEXT NOT NULL REFERENCES carrier(carrier_id),
  planned_departure_at TIMESTAMPTZ NOT NULL,
  planned_arrival_at TIMESTAMPTZ NOT NULL,
  actual_departure_at TIMESTAMPTZ,
  actual_arrival_at TIMESTAMPTZ,
  leg_status TEXT NOT NULL CHECK (leg_status IN ('PLANNED','IN_PROGRESS','COMPLETED','DISRUPTED','CANCELLED')),
  UNIQUE (shipment_id, leg_sequence),
  CHECK (planned_departure_at < planned_arrival_at),
  CHECK (actual_arrival_at IS NULL OR actual_departure_at IS NULL OR actual_departure_at <= actual_arrival_at)
);

CREATE TABLE IF NOT EXISTS tracking_event (
  event_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  leg_id TEXT REFERENCES shipment_leg(leg_id),
  facility_id TEXT REFERENCES facility(facility_id),
  event_type TEXT NOT NULL CHECK (event_type IN
    ('PICKUP','DEPARTED','ARRIVED','IN_TRANSIT','OUT_FOR_DELIVERY','DELIVERED','EXCEPTION','CUSTOMS_HOLD')),
  event_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL,
  source_event_key TEXT NOT NULL,
  is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (ingested_at >= event_at)
);

CREATE INDEX IF NOT EXISTS ix_event_shipment_event_at ON tracking_event(shipment_id, event_at);
CREATE INDEX IF NOT EXISTS ix_event_ingested_at ON tracking_event(ingested_at);
CREATE INDEX IF NOT EXISTS ix_event_source_key ON tracking_event(source_event_key);

CREATE TABLE IF NOT EXISTS facility_queue (
  queue_id TEXT PRIMARY KEY,
  facility_id TEXT NOT NULL REFERENCES facility(facility_id),
  observed_at TIMESTAMPTZ NOT NULL,
  queue_length INTEGER NOT NULL CHECK (queue_length >= 0),
  estimated_wait_minutes INTEGER NOT NULL CHECK (estimated_wait_minutes >= 0),
  capacity_utilization NUMERIC(5,3) NOT NULL CHECK (capacity_utilization BETWEEN 0 AND 1.5),
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ NOT NULL,
  CHECK (valid_from < valid_to)
);

CREATE TABLE IF NOT EXISTS weather_event (
  weather_event_id TEXT PRIMARY KEY,
  facility_id TEXT REFERENCES facility(facility_id),
  region TEXT NOT NULL,
  weather_type TEXT NOT NULL CHECK (weather_type IN ('RAIN','FLOOD','SNOW','WIND','FOG','HEAT')),
  severity TEXT NOT NULL CHECK (severity IN ('LOW','MODERATE','HIGH','SEVERE')),
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL,
  delay_factor NUMERIC(5,2) NOT NULL CHECK (delay_factor >= 1.0),
  CHECK (starts_at < ends_at)
);

CREATE TABLE IF NOT EXISTS eta_estimate (
  eta_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  prediction_at TIMESTAMPTZ NOT NULL,
  predicted_delivery_at TIMESTAMPTZ NOT NULL,
  predicted_delay_minutes INTEGER NOT NULL,
  delay_probability NUMERIC(6,5) NOT NULL CHECK (delay_probability BETWEEN 0 AND 1),
  model_version TEXT NOT NULL,
  feature_cutoff_at TIMESTAMPTZ NOT NULL,
  UNIQUE (shipment_id, prediction_at, model_version),
  CHECK (feature_cutoff_at = prediction_at)
);

CREATE TABLE IF NOT EXISTS delay_reason (
  delay_reason_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  reason_code TEXT NOT NULL CHECK (reason_code IN
    ('WEATHER','FACILITY_QUEUE','CARRIER','ROUTE_CHANGE','CUSTOMS','LATE_SCAN','OTHER')),
  reason_description TEXT NOT NULL,
  delay_minutes INTEGER NOT NULL CHECK (delay_minutes >= 0),
  observed_at TIMESTAMPTZ NOT NULL,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_primary_delay_reason
  ON delay_reason(shipment_id) WHERE is_primary = TRUE;

-- Effective-dated operating calendars.
CREATE TABLE IF NOT EXISTS carrier_calendar (
  carrier_calendar_id TEXT PRIMARY KEY,
  carrier_id TEXT NOT NULL REFERENCES carrier(carrier_id),
  weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  opens_at TIME NOT NULL, closes_at TIME NOT NULL,
  timezone TEXT NOT NULL,
  valid_from DATE NOT NULL, valid_to DATE,
  CHECK (opens_at < closes_at),
  CHECK (valid_to IS NULL OR valid_from < valid_to)
);

CREATE TABLE IF NOT EXISTS facility_calendar (
  facility_calendar_id TEXT PRIMARY KEY,
  facility_id TEXT NOT NULL REFERENCES facility(facility_id),
  weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  opens_at TIME NOT NULL, closes_at TIME NOT NULL,
  timezone TEXT NOT NULL,
  valid_from DATE NOT NULL, valid_to DATE,
  CHECK (opens_at < closes_at),
  CHECK (valid_to IS NULL OR valid_from < valid_to)
);

-- Append-only history tables: changes create rows; they do not overwrite prior state.
CREATE TABLE IF NOT EXISTS shipment_route_history (
  route_history_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  route_id TEXT NOT NULL REFERENCES route(route_id),
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to TIMESTAMPTZ,
  change_reason TEXT NOT NULL,
  CHECK (effective_to IS NULL OR effective_from < effective_to)
);
CREATE INDEX IF NOT EXISTS ix_route_history_shipment ON shipment_route_history(shipment_id, effective_from);

CREATE TABLE IF NOT EXISTS shipment_status_history (
  status_history_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  status TEXT NOT NULL CHECK (status IN
    ('CREATED','PICKED_UP','IN_TRANSIT','AT_FACILITY','OUT_FOR_DELIVERY','DELIVERED','EXCEPTION','CANCELLED')),
  effective_at TIMESTAMPTZ NOT NULL,
  source_event_id TEXT REFERENCES tracking_event(event_id),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_status_history_shipment ON shipment_status_history(shipment_id, effective_at);

-- Explicit many-to-many bridge for weather exposure along a shipment's route.
CREATE TABLE IF NOT EXISTS shipment_weather_exposure (
  exposure_id TEXT PRIMARY KEY,
  shipment_id TEXT NOT NULL REFERENCES shipment(shipment_id),
  weather_event_id TEXT NOT NULL REFERENCES weather_event(weather_event_id),
  exposed_from TIMESTAMPTZ NOT NULL,
  exposed_to TIMESTAMPTZ NOT NULL,
  CHECK (exposed_from < exposed_to),
  UNIQUE (shipment_id, weather_event_id, exposed_from)
);
