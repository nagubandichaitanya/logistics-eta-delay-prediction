
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Logistics Control Tower",
    page_icon="🚚",
    layout="wide"
)

ROOT = Path(__file__).resolve().parent

SHIPMENT_FILE = ROOT / "data" / "raw" / "shipment.csv"
GROUND_TRUTH_FILE = ROOT / "data" / "processed" / "ground_truth.csv"
TRACKING_FILE = ROOT / "data" / "raw" / "tracking_event.csv"

API_URL = "http://127.0.0.1:8000"


# --------------------------------------------------
# LOAD DASHBOARD DATA
# --------------------------------------------------

@st.cache_data
def load_dashboard_data():

    shipments = pd.read_csv(SHIPMENT_FILE)
    ground_truth = pd.read_csv(GROUND_TRUTH_FILE)

    # Convert text values into Boolean values.
    # Missing SLA values remain missing (unknown).

    ground_truth["is_delivered"] = (
        ground_truth["is_delivered"]
        .astype("string")
        .str.lower()
        .map({"true": True, "false": False})
        .astype("boolean")
    )

    ground_truth["is_sla_late"] = (
        ground_truth["is_sla_late"]
        .astype("string")
        .str.lower()
        .map({"true": True, "false": False})
        .astype("boolean")
    )

    data = shipments.merge(
        ground_truth[
            [
                "shipment_id",
                "is_delivered",
                "is_sla_late"
            ]
        ],
        on="shipment_id",
        how="left",
        validate="one_to_one"
    )

    # Display label only. This does not change the original SLA label.
    data["sla_status"] = (
        data["is_sla_late"]
        .map({
            True: "Late",
            False: "On Time"
        })
        .fillna("Pending")
    )

    return data


@st.cache_data
def load_tracking_data():

    tracking = pd.read_csv(TRACKING_FILE)

    tracking["event_at"] = pd.to_datetime(
        tracking["event_at"],
        utc=True
    )

    tracking["ingested_at"] = pd.to_datetime(
        tracking["ingested_at"],
        utc=True
    )

    # Exclude duplicate source events.
    tracking = tracking[
        tracking["is_duplicate"].astype(str).str.lower() == "false"
    ].copy()

    return tracking


# --------------------------------------------------
# MAIN HEADER
# --------------------------------------------------

st.title("🚚 Logistics Control Tower")

st.caption(
    "Shipment Monitoring | ETA Prediction | Delay Detection"
)

st.divider()


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

try:
    data = load_dashboard_data()
    tracking_data = load_tracking_data()

except Exception as error:
    st.error(f"Unable to load project data: {error}")
    st.stop()


# --------------------------------------------------
# API HEALTH STATUS
# --------------------------------------------------

st.subheader("System Health")

try:

    health_response = requests.get(
        f"{API_URL}/health",
        timeout=10
    )

    health_response.raise_for_status()
    health = health_response.json()

    if (
        health["status"] == "healthy"
        and health["eta_model_loaded"]
        and health["delay_model_loaded"]
        and health["feature_data_loaded"]
    ):
        st.success("All prediction services are operational.")

    else:
        st.warning("One or more prediction services are unavailable.")

    st.caption(
        f"Model Version: {health['model_version']}"
    )

except requests.exceptions.RequestException:

    st.error(
        "FastAPI is not running. Start the backend before "
        "using shipment predictions."
    )

    st.stop()


st.divider()


# --------------------------------------------------
# SHIPMENT OVERVIEW
# --------------------------------------------------

st.subheader("Shipment Overview")

total_shipments = len(data)

delivered = int(
    data["is_delivered"].eq(True).sum()
)

in_transit = int(
    data["is_delivered"].eq(False).sum()
)

delivered_late = int(
    (
        data["is_delivered"].eq(True)
        & data["is_sla_late"].eq(True)
    ).sum()
)

delivered_on_time = int(
    (
        data["is_delivered"].eq(True)
        & data["is_sla_late"].eq(False)
    ).sum()
)

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric(
    "Total Shipments",
    f"{total_shipments:,}"
)

col2.metric(
    "Delivered",
    f"{delivered:,}"
)

col3.metric(
    "In Transit",
    f"{in_transit:,}"
)

col4.metric(
    "Delivered Late",
    f"{delivered_late:,}"
)

col5.metric(
    "Delivered On Time",
    f"{delivered_on_time:,}"
)

st.caption(
    "In-transit shipments have a pending SLA outcome and are not "
    "counted as either delivered late or delivered on time."
)

st.divider()


# --------------------------------------------------
# SHIPMENT FILTERS
# --------------------------------------------------

st.subheader("Shipment Analytics")

col1, col2 = st.columns(2)

with col1:

    selected_status = st.selectbox(
        "Filter by Shipment Status",
        ["ALL"] + sorted(
            data["current_status"].dropna().unique().tolist()
        )
    )

with col2:

    selected_priority = st.selectbox(
        "Filter by Priority",
        ["ALL"] + sorted(
            data["priority"].dropna().unique().tolist()
        )
    )


filtered_data = data.copy()

if selected_status != "ALL":

    filtered_data = filtered_data[
        filtered_data["current_status"] == selected_status
    ]

if selected_priority != "ALL":

    filtered_data = filtered_data[
        filtered_data["priority"] == selected_priority
    ]


# --------------------------------------------------
# SHIPMENT ANALYTICS CHARTS
# --------------------------------------------------

chart_col1, chart_col2 = st.columns(2)

with chart_col1:

    st.markdown("#### Shipment Status Distribution")

    status_counts = data["current_status"].value_counts()

    st.bar_chart(status_counts)


with chart_col2:

    st.markdown("#### SLA Performance")

    sla_counts = pd.Series({
        "Delivered On Time": delivered_on_time,
        "Delivered Late": delivered_late,
        "In Transit - Pending": in_transit
    })

    st.bar_chart(sla_counts)


chart_col3, chart_col4 = st.columns(2)

with chart_col3:

    st.markdown("#### Priority Distribution")

    priority_counts = data["priority"].value_counts()

    st.bar_chart(priority_counts)


with chart_col4:

    st.markdown("#### Delivered Late Rate by Priority")

    # Only shipments with a known SLA outcome are included.
    known_sla_data = data[
        data["is_sla_late"].notna()
    ]

    priority_late = (
        known_sla_data
        .groupby("priority")["is_sla_late"]
        .mean()
        .mul(100)
        .round(2)
    )

    st.bar_chart(priority_late)


# --------------------------------------------------
# SHIPMENT RECORDS
# --------------------------------------------------

st.divider()

st.subheader("Shipment Records")

st.caption(
    f"Showing {len(filtered_data)} shipments based on your filters."
)

display_columns = [
    "shipment_id",
    "service_level_id",
    "origin_facility_id",
    "destination_facility_id",
    "current_status",
    "priority",
    "weight_kg",
    "sla_status"
]

st.dataframe(
    filtered_data[display_columns],
    use_container_width=True,
    hide_index=True
)


# --------------------------------------------------
# SHIPMENT ETA AND DELAY PREDICTION
# --------------------------------------------------

st.divider()

st.title("🔮 Shipment ETA & Delay Prediction")

st.write(
    "Select a shipment to generate an estimated delivery time "
    "and delay probability using trained machine learning models."
)

st.info(
    "Prediction uses the latest available historical feature snapshot "
    "for the selected shipment. It does not represent a live GPS update."
)


# --------------------------------------------------
# SELECT SHIPMENT
# --------------------------------------------------

shipment_ids = sorted(
    data["shipment_id"].dropna().unique().tolist()
)

selected_shipment = st.selectbox(
    "Select Shipment ID",
    shipment_ids
)

shipment_record = data[
    data["shipment_id"] == selected_shipment
].iloc[0]


# --------------------------------------------------
# SHIPMENT TRACKING TIMELINE
# --------------------------------------------------

st.divider()

st.subheader("📍 Shipment Tracking Timeline")

shipment_events = tracking_data[
    tracking_data["shipment_id"] == selected_shipment
].copy()

shipment_events = shipment_events.sort_values(
    "event_at"
)

if shipment_events.empty:

    st.warning("No tracking events found for this shipment.")

else:

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Total Tracking Events",
        len(shipment_events)
    )

    col2.metric(
        "Route Legs",
        shipment_events["leg_id"].nunique()
    )

    col3.metric(
        "Facilities Visited",
        shipment_events["facility_id"].nunique()
    )

    st.markdown("#### Shipment Journey")

    for _, event in shipment_events.iterrows():

        event_name = event["event_type"]

        st.markdown(
            f"""
            **{event_name}**
            - Event ID: `{event['event_id']}`
            - Facility: `{event['facility_id']}`
            - Route Leg: `{event['leg_id']}`
            - Event Time: {event['event_at']}
            - Ingested Time: {event['ingested_at']}
            """
        )

        st.divider()

    with st.expander("View All Tracking Records"):

        st.dataframe(
            shipment_events[
                [
                    "event_id",
                    "event_type",
                    "facility_id",
                    "leg_id",
                    "event_at",
                    "ingested_at"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )


# --------------------------------------------------
# SELECTED SHIPMENT DETAILS
# --------------------------------------------------

st.subheader("Selected Shipment Details")

col1, col2, col3 = st.columns(3)

col1.metric(
    "Current Status",
    shipment_record["current_status"]
)

col2.metric(
    "Priority",
    shipment_record["priority"]
)

if pd.isna(shipment_record["is_sla_late"]):

    actual_sla_status = "Pending"

elif shipment_record["is_sla_late"]:

    actual_sla_status = "Late"

else:

    actual_sla_status = "On Time"

col3.metric(
    "Actual SLA Status",
    actual_sla_status
)


# --------------------------------------------------
# RUN ETA AND DELAY PREDICTION
# --------------------------------------------------

if st.button(
    "Predict ETA and Delay",
    type="primary",
    use_container_width=True
):

    try:

        with st.spinner("Running machine learning predictions..."):

            response = requests.post(
                f"{API_URL}/predict/delay",
                json={
                    "shipment_id": selected_shipment
                },
                timeout=60
            )

            response.raise_for_status()
            result = response.json()

        st.success("Prediction completed successfully!")

        st.divider()

        # ETA RESULTS

        st.subheader("ETA Prediction")

        col1, col2 = st.columns(2)

        col1.metric(
            "Estimated Delivery",
            result["estimated_delivery_at"]
        )

        col2.metric(
            "Remaining Delivery Time",
            f"{result['remaining_delivery_minutes']:.2f} minutes"
        )

        # DELAY RESULTS

        st.subheader("Delay Detection")

        col1, col2 = st.columns(2)

        col1.metric(
            "Delay Probability",
            f"{result['delay_probability'] * 100:.2f}%"
        )

        col2.metric(
            "Predicted Delay",
            f"{result['predicted_delay_minutes']} minutes"
        )

        if result["is_delay_likely"]:

            st.error(
                "⚠️ The model predicts a likely delivery delay."
            )

        else:

            st.success(
                "✅ The model does not predict a likely delivery delay."
            )

        # PREDICTION INFORMATION

        st.subheader("Prediction Information")

        st.write("**Shipment ID:**", result["shipment_id"])
        st.write("**Prediction ID:**", result["eta_id"])
        st.write("**Prediction Time:**", result["prediction_at"])
        st.write("**Model Version:**", result["model_version"])

        with st.expander("View Complete Prediction Response"):

            st.json(result)

    except requests.exceptions.HTTPError:

        try:

            detail = response.json().get(
                "detail",
                response.text
            )

        except ValueError:

            detail = response.text

        st.error(f"Prediction API error: {detail}")

    except requests.exceptions.RequestException as error:

        st.error(f"Connection error: {error}")

    except (KeyError, ValueError) as error:

        st.error(f"Unexpected prediction response: {error}")


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

st.caption(
    "Logistics ETA Prediction and Delay Detection System | "
    "Python • PostgreSQL • Scikit-learn • FastAPI • Streamlit"
)
