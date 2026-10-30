# Data dictionary (Stage 1 contract)

All timestamps are UTC ISO-8601 values. All primary keys are immutable strings.
Required means NOT NULL. IDs follow the naming convention in the specification.
Effective-dated records use inclusive `valid_from` and exclusive `valid_to` intervals.

## Core entities

### Carrier
- `carrier_id` TEXT, required, unique PK; `CAR-000001` format.
- `carrier_name` TEXT, required; non-empty.
- `carrier_type` TEXT, required; `ROAD`, `AIR`, `RAIL`, `OCEAN`, `MULTIMODAL`.
- `active` BOOLEAN, required; lifecycle flag.
- `created_at` TIMESTAMPTZ, required.

### Facility
- `facility_id` TEXT, required, unique PK; `FAC-000001` format.
- `facility_name` TEXT, required.
- `facility_type` TEXT, required; `ORIGIN`, `HUB`, `WAREHOUSE`, `PORT`, `DESTINATION`.
- `city`, `state`, `country` TEXT, required.
- `timezone` TEXT, required; IANA timezone identifier.
- `capacity_per_hour` INTEGER, required; > 0, units: shipments/hour.
- `created_at` TIMESTAMPTZ, required.

### Route
- `route_id` TEXT, required, unique PK; `RTE-000001` format.
- `origin_facility_id`, `destination_facility_id` TEXT, required FKs to Facility.
- `distance_km` NUMERIC, required; > 0, units: km.
- `transport_mode` TEXT, required; `ROAD`, `AIR`, `RAIL`, `OCEAN`.
- `created_at` TIMESTAMPTZ, required.

### ServiceLevel
- `service_level_id` TEXT, required, unique PK; `SLA-000001` format.
- `service_name` TEXT, required.
- `target_hours` NUMERIC, required; > 0, units: hours.
- `late_grace_minutes` INTEGER, required; >= 0, units: minutes.
- `active` BOOLEAN, required.

### Shipment
- `shipment_id` TEXT, required, unique PK; `SHP-2026-000001` format.
- `service_level_id` TEXT, required FK to ServiceLevel.
- `origin_facility_id`, `destination_facility_id` TEXT, required FKs to Facility.
- `created_at`, `planned_pickup_at`, `promised_delivery_at` TIMESTAMPTZ, required.
- `actual_delivery_at` TIMESTAMPTZ, optional; populated only when delivered.
- `current_status` TEXT, required; `CREATED`, `PICKED_UP`, `IN_TRANSIT`, `AT_FACILITY`, `OUT_FOR_DELIVERY`, `DELIVERED`, `EXCEPTION`, `CANCELLED`.
- `priority` TEXT, required; `LOW`, `STANDARD`, `HIGH`, `CRITICAL`.
- `weight_kg` NUMERIC, required; > 0, units: kg.
- `created_at <= planned_pickup_at <= promised_delivery_at`; actual delivery cannot precede pickup.

### ShipmentLeg
- `leg_id` TEXT, required, unique PK; `LEG-{shipment_id}-01` format.
- `shipment_id` TEXT, required FK to Shipment.
- `leg_sequence` INTEGER, required; >= 1; unique with shipment_id.
- `route_id`, `carrier_id` TEXT, required FKs.
- `planned_departure_at`, `planned_arrival_at` TIMESTAMPTZ, required; departure < arrival.
- `actual_departure_at`, `actual_arrival_at` TIMESTAMPTZ, optional.
- `leg_status` TEXT, required; `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `DISRUPTED`, `CANCELLED`.
- A shipment has 1:N legs; leg sequence is contiguous and route endpoints must connect.

### TrackingEvent
- `event_id` TEXT, required, unique PK; `EVT-{shipment_id}-000001` format.
- `shipment_id` TEXT, required FK to Shipment.
- `leg_id` TEXT, optional FK to ShipmentLeg.
- `facility_id` TEXT, optional FK to Facility.
- `event_type` TEXT, required; `PICKUP`, `DEPARTED`, `ARRIVED`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`, `EXCEPTION`, `CUSTOMS_HOLD`.
- `event_at` TIMESTAMPTZ, required; when event happened.
- `ingested_at` TIMESTAMPTZ, required; when platform received it; may be later than event_at.
- `source_event_key` TEXT, required; carrier/source idempotency key.
- `is_duplicate` BOOLEAN, required; duplicate scan indicator.
- `created_at` TIMESTAMPTZ, required.
- Duplicate source keys are retained for audit; canonical-event selection is deterministic.

### FacilityQueue
- `queue_id` TEXT, required, unique PK; `QUE-000001` format.
- `facility_id` TEXT, required FK to Facility.
- `observed_at` TIMESTAMPTZ, required.
- `queue_length` INTEGER, required; >= 0, units: shipments.
- `estimated_wait_minutes` INTEGER, required; >= 0, units: minutes.
- `capacity_utilization` NUMERIC, required; range [0, 1.5], ratio.
- `valid_from`, `valid_to` TIMESTAMPTZ, required; valid_from < valid_to.

### WeatherEvent
- `weather_event_id` TEXT, required, unique PK; `WTH-000001` format.
- `facility_id` TEXT, optional FK to Facility; null means regional event.
- `region` TEXT, required.
- `weather_type` TEXT, required; `RAIN`, `FLOOD`, `SNOW`, `WIND`, `FOG`, `HEAT`.
- `severity` TEXT, required; `LOW`, `MODERATE`, `HIGH`, `SEVERE`.
- `starts_at`, `ends_at` TIMESTAMPTZ, required; starts_at < ends_at.
- `delay_factor` NUMERIC, required; >= 1.0 multiplier.

### ETAEstimate
- `eta_id` TEXT, required, unique PK; `ETA-{shipment_id}-{timestamp}` format.
- `shipment_id` TEXT, required FK to Shipment.
- `prediction_at` TIMESTAMPTZ, required; prediction cutoff.
- `predicted_delivery_at` TIMESTAMPTZ, required.
- `predicted_delay_minutes` INTEGER, required; may be negative for early prediction.
- `delay_probability` NUMERIC, required; range [0,1].
- `model_version` TEXT, required.
- `feature_cutoff_at` TIMESTAMPTZ, required; must equal prediction_at.
- Unique `(shipment_id, prediction_at, model_version)`.

### DelayReason
- `delay_reason_id` TEXT, required, unique PK; `DLY-2026-000001` format.
- `shipment_id` TEXT, required FK to Shipment.
- `reason_code` TEXT, required; `WEATHER`, `FACILITY_QUEUE`, `CARRIER`, `ROUTE_CHANGE`, `CUSTOMS`, `LATE_SCAN`, `OTHER`.
- `reason_description` TEXT, required.
- `delay_minutes` INTEGER, required; >= 0.
- `observed_at` TIMESTAMPTZ, required.
- `is_primary` BOOLEAN, required; at most one primary reason per shipment.

## Supporting relationship/history tables

- `carrier_calendar`: carrier_id FK, weekday, local start/end time, timezone, effective dates.
- `facility_calendar`: facility_id FK, weekday, local start/end time, timezone, effective dates.
- `shipment_route_history`: shipment_id FK, route_id FK, effective_from/effective_to, change_reason; preserves route changes.
- `shipment_status_history`: shipment_id FK, status, effective_at, source_event_id optional FK; append-only lifecycle history.
- `ground_truth`: deliberately kept outside operational schema and exported separately; includes case_id, entity_id, issue_type, expected_decision, label, details. Never used as model features.

## Cardinality and optionality

- ServiceLevel 1:N Shipment.
- Facility 1:N Shipment as origin and destination (two separately named FKs).
- Shipment 1:N ShipmentLeg.
- Route 1:N ShipmentLeg; Carrier 1:N ShipmentLeg.
- Shipment 1:N TrackingEvent; ShipmentLeg 1:N TrackingEvent (optional leg link).
- Facility 1:N FacilityQueue.
- Facility 1:N WeatherEvent when facility-specific; WeatherEvent facility link is optional.
- Shipment 1:N ETAEstimate and Shipment 1:N DelayReason.
- Shipment N:M Route over time, resolved by `shipment_route_history`.
- Carrier N:M weekday operating windows, resolved by `carrier_calendar`.
- Facility N:M weekday operating windows, resolved by `facility_calendar`.
