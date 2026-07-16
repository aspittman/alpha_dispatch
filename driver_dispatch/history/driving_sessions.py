from driver_dispatch.models import DrivingSession


def session_from_args(args) -> DrivingSession:
    start, end = args.start, args.end
    return DrivingSession(date=start.date(), start_datetime=start, end_datetime=end, starting_area=args.starting_area, ending_area=args.ending_area, gross_earnings=args.gross, tips=args.tips, bonuses=args.bonuses, miles_driven=args.miles, estimated_fuel_cost=args.fuel, trips_completed=args.trips, event_targeted=args.event, time_waiting=args.waiting, deadhead_miles=args.deadhead, notes=args.notes)

