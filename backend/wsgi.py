from app import app as application

# For WSGI servers like gunicorn/uwsgi, the entry point is `application`
# Example: gunicorn -w 2 -b 0.0.0.0:5000 wsgi:application
