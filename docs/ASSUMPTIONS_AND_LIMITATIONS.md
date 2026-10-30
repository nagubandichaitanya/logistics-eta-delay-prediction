# Assumptions, Trade-offs, and Limitations

## 1. Project Overview

The Logistics ETA Prediction and Delay Detection System estimates shipment delivery times and identifies potential delays using shipment details, route information, carrier events, facility queues, and weather disruptions.

The current implementation uses reproducible synthetic data and is intended as a prototype rather than a production logistics platform.

## 2. Assumptions

### Shipment and Route Assumptions

- Every shipment has a unique shipment ID.
- A shipment can contain one or more sequential route legs.
- Route legs must connect correctly: the destination facility of one leg must match the origin facility of the next leg.
- A shipment is considered delivered only when its status and delivery event information are consistent.
- The current synthetic generator assigns one carrier to a shipment and uses that carrier across its legs.

### Tracking Event Assumptions

- `event_at` represents when an event actually occurred.
- `ingested_at` represents when the system received the event.
- An event can be used for an ETA prediction only if both timestamps are at or before the prediction timestamp.
- Duplicate tracking records are identified and excluded from feature calculations.

### ETA and Delay Assumptions

- ETA predictions are generated at 0-hour, 12-hour, and 24-hour snapshots after planned pickup.
- A shipment delivered before a snapshot is excluded from that snapshot.
- Ground-truth labels are maintained separately from model features.
- A shipment is classified as late using its actual delivery time or, for undelivered shipments, its observation status at the defined cutoff.
- Delay minutes are calculated relative to the promised delivery time. SLA grace periods are stored separately and must be considered when interpreting SLA performance.

### Weather and Facility Assumptions

- Weather disruptions are associated with facilities and active time windows.
- Facility queue utilization is represented as a ratio.
- Weather availability is assumed from the disruption start time because the current weather dataset does not contain a separate ingestion timestamp. This is a limitation when simulating information availability in a real-time prediction system.

## 3. Implementation Trade-offs

| Decision | Reason | Trade-off |
|---|---|---|
| Synthetic data | Allows repeatable development without requiring private carrier data. | Does not represent all real-world logistics patterns. |
| Starter dataset of 1,000 shipments | Makes development and testing manageable. | Smaller than the full 50,000-shipment target. |
| Fixed random seed | Makes generated datasets reproducible. | Different seeds may produce different distributions. |
| PostgreSQL | Provides relational integrity and structured data storage. | Requires database setup and configuration. |
| Pandas and NumPy | Support data generation, transformation, and feature engineering. | Large datasets may require more memory and optimization. |
| Time-based snapshots | Simulate ETA predictions at different shipment stages. | Only three snapshot intervals are currently implemented. |
| Separate ground-truth data | Reduces the risk of target leakage into model features. | Requires careful alignment of feature and label records. |

## 4. Current Limitations

1. **Synthetic data:** The data is generated rather than collected from actual carriers, warehouses, and weather services.
2. **Weather ingestion time:** Weather records do not currently have a separate ingestion timestamp. The feature pipeline assumes the disruption is known from its start time.
3. **Snapshot frequency:** Predictions are generated at fixed 0-hour, 12-hour, and 24-hour intervals rather than continuously.
4. **Carrier behavior:** The current generator does not fully model individual carrier reliability, operational policies, or changing carrier assignments.
5. **Facility operations:** Queue and calendar data are simplified representations of real warehouse capacity and operating schedules.
6. **Model generalization:** Model performance on synthetic data does not establish accuracy on real logistics data.
7. **Scalability:** The starter configuration has been tested at 1,000 shipments. The full-scale configuration requires additional performance and memory testing.
8. **External integrations:** Live carrier APIs, GPS feeds, weather services, and warehouse management systems are not currently integrated.
9. **Operational deployment:** Authentication, authorization, monitoring, production infrastructure, and automated model retraining require further development.

## 5. Future Improvements

- Integrate real carrier tracking APIs and GPS information.
- Include weather event ingestion timestamps and historical weather observations.
- Increase prediction frequency and support event-triggered ETA updates.
- Add carrier-specific performance and route-level historical statistics.
- Improve facility congestion modeling using real queue and capacity data.
- Benchmark performance at the full 50,000-shipment scale.
- Evaluate models using chronological train, validation, and test splits.
- Monitor prediction errors and retrain models when operational data changes.
- Add API authentication, logging, monitoring, and production deployment support.

## 6. Conclusion

The current implementation provides a reproducible foundation for logistics ETA estimation and delay detection. It demonstrates synthetic data generation, relational database design, temporal feature engineering, data validation, negative-scenario testing, and model development.

Its outputs should be treated as prototype results. Real-world accuracy and operational readiness require validation with historical and live logistics data.
