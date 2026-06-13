"""
Agent tools — weather, places, hotels, transport.

All tools follow the same contract:
    - Check for API key in settings → use real API if available
    - Fall back to realistic mock data if no key (dev/test friendly)
    - Always async, always have timeout
    - Failures logged as warnings — never crash the agent pipeline
"""
