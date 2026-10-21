import time

# renew at most every few minutes, so ordinary page views don't all write the session
RENEW_EVERY = 5 * 60


class IdleTimeoutMiddleware:
    """Keeps a signed-in session alive while it is used; after SESSION_COOKIE_AGE without use it expires.

    The session cookie and the stored session both expire SESSION_COOKIE_AGE after their last save,
    so touching the session every few minutes turns that into an idle timeout.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = int(time.time())
            if now - request.session.get('seen', 0) > RENEW_EVERY:
                request.session['seen'] = now
        return self.get_response(request)

