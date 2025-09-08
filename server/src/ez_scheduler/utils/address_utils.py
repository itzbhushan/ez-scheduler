"""Address utility functions"""

import urllib.parse


def generate_google_maps_url(address: str) -> str:
    """
    Generate a Google Maps URL from an address string.

    Args:
        address: The address string to convert to a Google Maps URL

    Returns:
        A Google Maps URL that opens the address location
    """
    if not address or not address.strip():
        return ""

    # URL encode the address for use in the Google Maps URL
    encoded_address = urllib.parse.quote_plus(address.strip())

    # Create the Google Maps URL
    return f"https://www.google.com/maps/search/?api=1&query={encoded_address}"
