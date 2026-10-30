
from dataclasses import dataclass
from pathlib import Path


# Find the root project directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class GeneratorConfig:
    # Reproducible random seed
    seed: int = 20261022

    # Starter dataset sizes
    num_shipments: int = 1000
    num_facilities: int = 100
    num_disruption_windows: int = 1000

    # Approximate tracking events per shipment
    events_per_shipment: int = 6

    # Output directories
    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_data_dir: Path = PROJECT_ROOT / "data" / "processed"
    reports_dir: Path = PROJECT_ROOT / "reports"

    def validate(self):
        if self.seed < 0:
            raise ValueError("Seed cannot be negative.")

        if self.num_shipments <= 0:
            raise ValueError("Number of shipments must be positive.")

        if self.num_facilities <= 0:
            raise ValueError("Number of facilities must be positive.")

        if self.num_disruption_windows < 0:
            raise ValueError("Disruption windows cannot be negative.")

        if self.events_per_shipment < 2:
            raise ValueError("At least two events per shipment are required.")

    def create_directories(self):
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


# Default starter configuration
DEFAULT_CONFIG = GeneratorConfig()
