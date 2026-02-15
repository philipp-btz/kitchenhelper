from app import app

# Expose the Flask `app` as the WSGI callable named `application`
# so servers like Gunicorn or Waitress can import it as `wsgi:application`.
application = app
