from django.dispatch import Signal

AggregatorUpdate = Signal(providing_args=['aggregation_data'])
