def get_client_ip(request):
    """IP de origem da requisição. Atrás de proxy (Railway) o IP real vem no X-Forwarded-For."""
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent(request):
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:300]
