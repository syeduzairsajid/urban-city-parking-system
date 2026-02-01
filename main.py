from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import math
import uuid


# =========================================================
# Utility functions
# =========================================================
def ceil_hours(duration_seconds: float) -> int:
    """
    Round up duration (seconds) to the next full hour.
    Minimum billed time is 1 hour.
    """
    hours = duration_seconds / 3600.0
    billed = math.ceil(hours)
    return max(1, billed)


def is_weekend(dt: datetime) -> bool:
    """Return True if dt is Saturday(5) or Sunday(6)."""
    return dt.weekday() >= 5


# =========================================================
# Abstract Base Classes (ABC) - Required
# =========================================================
class Vehicle(ABC):
    """Abstract base class for all vehicles."""

    def __init__(self, plate: str):
        self.plate = plate.strip().upper()

    @property
    @abstractmethod
    def vehicle_type(self) -> str:
        pass

    @property
    @abstractmethod
    def multiplier(self) -> float:
        pass


class Pass(ABC):
    """Abstract base class for all pass types (Monthly, SingleEntry)."""

    def __init__(self, plate: str):
        self.pass_id = str(uuid.uuid4())[:8].upper()
        self.plate = plate.strip().upper()

    @property
    @abstractmethod
    def pass_type(self) -> str:
        pass

    @abstractmethod
    def is_valid(self, at_time: datetime) -> bool:
        pass


class PricingStrategy(ABC):
    """Abstract base class for pricing strategies."""

    @abstractmethod
    def calculate_price(
        self,
        duration_seconds: float,
        vehicle: Vehicle,
        entry_time: datetime,
        exit_time: datetime
    ) -> float:
        pass

    @abstractmethod
    def rule_name(self) -> str:
        pass


# =========================================================
# Vehicle subclasses (Inheritance) - Required
# =========================================================
class Car(Vehicle):
    @property
    def vehicle_type(self) -> str:
        return "Car"

    @property
    def multiplier(self) -> float:
        return 1.0


class Motorcycle(Vehicle):
    @property
    def vehicle_type(self) -> str:
        return "Motorcycle"

    @property
    def multiplier(self) -> float:
        return 0.8


class Truck(Vehicle):
    @property
    def vehicle_type(self) -> str:
        return "Truck"

    @property
    def multiplier(self) -> float:
        return 1.5


# =========================================================
# Pass subclasses (Inheritance) - Required
# =========================================================
class MonthlyPass(Pass):
    def __init__(self, plate: str, start_date: date, end_date: date):
        super().__init__(plate)
        self.start_date = start_date
        self.end_date = end_date

    @property
    def pass_type(self) -> str:
        return "MonthlyPass"

    def is_valid(self, at_time: datetime) -> bool:
        today = at_time.date()
        return self.start_date <= today <= self.end_date


class SingleEntryPass(Pass):
    def __init__(self, plate: str):
        super().__init__(plate)
        self.used = False

    @property
    def pass_type(self) -> str:
        return "SingleEntryPass"

    def is_valid(self, at_time: datetime) -> bool:
        return not self.used

    def mark_used(self) -> None:
        self.used = True


# =========================================================
# Upgraded Pricing Strategy (Hour-by-hour)
# =========================================================
class HourlyPricingStrategy(PricingStrategy):
    """
    Charges parking hour-by-hour (rounded up to full hours).
    - Weekend (Sat/Sun): $5/hr
    - Weekday Peak (08:00–18:00): $6/hr
    - Weekday Off-peak: $4/hr
    Each hour uses the rate based on that hour's timestamp.
    """

    def calculate_price(
        self,
        duration_seconds: float,
        vehicle: Vehicle,
        entry_time: datetime,
        exit_time: datetime
    ) -> float:
        total_fee = 0.0
        billed_hours = ceil_hours(duration_seconds)

        current_time = entry_time
        for _ in range(billed_hours):
            if is_weekend(current_time):
                base_rate = 5.0
            else:
                if 8 <= current_time.hour < 18:
                    base_rate = 6.0
                else:
                    base_rate = 4.0

            total_fee += base_rate * vehicle.multiplier
            current_time += timedelta(hours=1)

        return round(total_fee, 2)

    def rule_name(self) -> str:
        return "Hourly Pricing (Peak/Off-peak/Weekend)"


# =========================================================
# Core domain classes
# =========================================================
@dataclass
class ParkingSpot:
    spot_id: int
    is_occupied: bool = False
    current_plate: str | None = None

    def occupy(self, plate: str) -> None:
        self.is_occupied = True
        self.current_plate = plate

    def vacate(self) -> None:
        self.is_occupied = False
        self.current_plate = None


@dataclass
class ParkingSession:
    ticket_id: str
    vehicle: Vehicle
    spot_id: int
    entry_time: datetime
    pass_used: Pass | None = None
    exit_time: datetime | None = None

    def close(self, exit_time: datetime) -> None:
        self.exit_time = exit_time

    def duration_seconds(self) -> float:
        if self.exit_time is None:
            return 0.0
        return (self.exit_time - self.entry_time).total_seconds()


@dataclass
class Receipt:
    ticket_id: str
    plate: str
    entry_time: datetime
    exit_time: datetime
    fee: float
    rule: str
    spot_id: int
    vehicle_type: str
    pass_info: str


# =========================================================
# Pass Manager
# =========================================================
class PassManager:
    """Stores and manages passes."""

    def __init__(self):
        self._passes: dict[str, Pass] = {}

    def create_monthly_pass(self, plate: str, start_date: date, end_date: date) -> MonthlyPass:
        mp = MonthlyPass(plate, start_date, end_date)
        self._passes[mp.pass_id] = mp
        return mp

    def create_single_entry_pass(self, plate: str) -> SingleEntryPass:
        sp = SingleEntryPass(plate)
        self._passes[sp.pass_id] = sp
        return sp

    def get_pass(self, pass_id: str) -> Pass | None:
        return self._passes.get(pass_id.strip().upper())

    def find_valid_monthly_pass(self, plate: str, at_time: datetime) -> MonthlyPass | None:
        plate = plate.strip().upper()
        for p in self._passes.values():
            if isinstance(p, MonthlyPass) and p.plate == plate and p.is_valid(at_time):
                return p
        return None


# =========================================================
# Fee Calculator (Upgraded)
# =========================================================
class FeeCalculator:
    """
    Computes fees using the upgraded hour-by-hour pricing model.
    Pass rules:
    - Valid MonthlyPass => fee = 0
    - SingleEntryPass => fee = 0 for one session, then mark used
    """

    def __init__(self):
        self.strategy: PricingStrategy = HourlyPricingStrategy()

    def compute_fee(self, session: ParkingSession, pass_manager: PassManager) -> tuple[float, str, str]:
        assert session.exit_time is not None, "Session must be closed before fee calculation."

        # 1) If a pass was explicitly used, validate it
        if session.pass_used is not None:
            p = session.pass_used

            if not p.is_valid(session.exit_time):
                # Invalid pass -> charge normally
                pass_info = f"{p.pass_type} INVALID (charged normally)"
            else:
                # Valid monthly => free
                if isinstance(p, MonthlyPass):
                    return 0.0, "MonthlyPass Applied", "MonthlyPass VALID (fee waived)"

                # Valid single entry => free once, then mark used
                if isinstance(p, SingleEntryPass):
                    p.mark_used()
                    return 0.0, "SingleEntryPass Applied", "SingleEntryPass USED (fee waived)"

                pass_info = f"{p.pass_type} VALID"
        else:
            pass_info = "No pass"

        # 2) Optional: auto-detect valid monthly pass by plate (even if user didn't enter pass id)
        auto_mp = pass_manager.find_valid_monthly_pass(session.vehicle.plate, session.exit_time)
        if auto_mp is not None:
            return 0.0, "MonthlyPass Auto-Detected", "MonthlyPass VALID (fee waived)"

        # 3) Normal pricing (hour-by-hour)
        fee = self.strategy.calculate_price(
            duration_seconds=session.duration_seconds(),
            vehicle=session.vehicle,
            entry_time=session.entry_time,
            exit_time=session.exit_time
        )
        return fee, self.strategy.rule_name(), pass_info


# =========================================================
# Parking Lot (Main system)
# =========================================================
class ParkingLot:
    """
    Manages:
    - 300 parking spots
    - space allocation/release
    - active sessions
    - passes
    - fee calculation
    """

    def __init__(self, capacity: int = 300):
        self.capacity = capacity
        self.spots = [ParkingSpot(spot_id=i + 1) for i in range(capacity)]
        self.active_sessions_by_plate: dict[str, ParkingSession] = {}
        self.active_sessions_by_ticket: dict[str, ParkingSession] = {}
        self.pass_manager = PassManager()
        self.fee_calculator = FeeCalculator()

    # ----- Availability -----
    def has_availability(self) -> bool:
        return any(not s.is_occupied for s in self.spots)

    def available_count(self) -> int:
        return sum(1 for s in self.spots if not s.is_occupied)

    # ----- Spot handling -----
    def allocate_spot(self, vehicle: Vehicle) -> ParkingSpot:
        for s in self.spots:
            if not s.is_occupied:
                s.occupy(vehicle.plate)
                return s
        raise RuntimeError("Parking lot is full (no spots available).")

    def release_spot(self, spot_id: int) -> None:
        if 1 <= spot_id <= self.capacity:
            self.spots[spot_id - 1].vacate()

    # ----- Sessions -----
    def start_session(self, vehicle: Vehicle, pass_id: str | None = None) -> ParkingSession:
        if vehicle.plate in self.active_sessions_by_plate:
            raise ValueError("This vehicle already has an active session.")

        if not self.has_availability():
            raise RuntimeError("No spots available (parking lot full).")

        used_pass: Pass | None = None
        if pass_id:
            p = self.pass_manager.get_pass(pass_id)
            if p is None:
                raise ValueError("Pass ID not found.")
            if p.plate != vehicle.plate:
                raise ValueError("Pass plate does not match vehicle plate.")
            used_pass = p

        spot = self.allocate_spot(vehicle)
        ticket_id = "T-" + str(uuid.uuid4())[:8].upper()

        session = ParkingSession(
            ticket_id=ticket_id,
            vehicle=vehicle,
            spot_id=spot.spot_id,
            entry_time=datetime.now(),
            pass_used=used_pass
        )

        self.active_sessions_by_plate[vehicle.plate] = session
        self.active_sessions_by_ticket[ticket_id] = session
        return session

    def end_session(self, identifier: str) -> Receipt:
        key = identifier.strip().upper()

        session = self.active_sessions_by_ticket.get(key)
        if session is None:
            session = self.active_sessions_by_plate.get(key)

        if session is None:
            raise ValueError("No active session found for that ticket/plate.")

        exit_time = datetime.now()
        session.close(exit_time)

        fee, rule, pass_info = self.fee_calculator.compute_fee(session, self.pass_manager)

        # release spot and remove active session
        self.release_spot(session.spot_id)
        del self.active_sessions_by_plate[session.vehicle.plate]
        del self.active_sessions_by_ticket[session.ticket_id]

        return Receipt(
            ticket_id=session.ticket_id,
            plate=session.vehicle.plate,
            entry_time=session.entry_time,
            exit_time=session.exit_time,
            fee=fee,
            rule=rule,
            spot_id=session.spot_id,
            vehicle_type=session.vehicle.vehicle_type,
            pass_info=pass_info
        )


# =========================================================
# Console UI (Simple working demo)
# =========================================================
def build_vehicle(vehicle_type: str, plate: str) -> Vehicle:
    vt = vehicle_type.strip().lower()
    if vt == "car":
        return Car(plate)
    if vt == "motorcycle":
        return Motorcycle(plate)
    if vt == "truck":
        return Truck(plate)
    raise ValueError("Invalid vehicle type. Use Car/Motorcycle/Truck.")


def parse_date(yyyy_mm_dd: str) -> date:
    parts = yyyy_mm_dd.strip().split("-")
    if len(parts) != 3:
        raise ValueError("Date must be in YYYY-MM-DD format.")
    y, m, d = [int(x) for x in parts]
    return date(y, m, d)


def print_receipt(r: Receipt) -> None:
    print("\n========== RECEIPT ==========")
    print(f"Ticket ID   : {r.ticket_id}")
    print(f"Plate       : {r.plate}")
    print(f"Vehicle Type: {r.vehicle_type}")
    print(f"Spot ID     : {r.spot_id}")
    print(f"Entry Time  : {r.entry_time}")
    print(f"Exit Time   : {r.exit_time}")
    print(f"Rule Applied: {r.rule}")
    print(f"Pass Info   : {r.pass_info}")
    print(f"Total Fee   : ${r.fee:.2f}")
    print("=============================\n")


def main():
    lot = ParkingLot(capacity=300)

    while True:
        print("=== Urban City Parking System ===")
        print(f"Available spots: {lot.available_count()} / {lot.capacity}")
        print("1) Create Monthly Pass")
        print("2) Create Single Entry Pass")
        print("3) Vehicle Entry (Start Session)")
        print("4) Vehicle Exit (End Session)")
        print("5) Exit Program")

        choice = input("Choose an option: ").strip()

        try:
            if choice == "1":
                plate = input("Enter plate number: ")
                start = parse_date(input("Start date (YYYY-MM-DD): "))
                end = parse_date(input("End date (YYYY-MM-DD): "))
                mp = lot.pass_manager.create_monthly_pass(plate, start, end)
                print(f"\nMonthly pass created.")
                print(f"Pass ID: {mp.pass_id} | Plate: {mp.plate} | {mp.start_date} to {mp.end_date}\n")

            elif choice == "2":
                plate = input("Enter plate number: ")
                sp = lot.pass_manager.create_single_entry_pass(plate)
                print(f"\nSingle entry pass created.")
                print(f"Pass ID: {sp.pass_id} | Plate: {sp.plate}\n")

            elif choice == "3":
                plate = input("Plate number: ")
                vtype = input("Vehicle type (Car/Motorcycle/Truck): ")
                pass_id = input("Pass ID (press Enter if none): ").strip()
                vehicle = build_vehicle(vtype, plate)

                session = lot.start_session(vehicle, pass_id if pass_id else None)
                print("\nVehicle entered successfully!")
                print(f"Ticket ID: {session.ticket_id}")
                print(f"Spot ID  : {session.spot_id}")
                print(f"Entry    : {session.entry_time}\n")

            elif choice == "4":
                identifier = input("Enter Ticket ID or Plate: ")
                receipt = lot.end_session(identifier)
                print_receipt(receipt)

            elif choice == "5":
                print("Goodbye!")
                break

            else:
                print("Invalid choice.\n")

        except Exception as ex:
            print(f"\nERROR: {ex}\n")


if __name__ == "__main__":
    main()
