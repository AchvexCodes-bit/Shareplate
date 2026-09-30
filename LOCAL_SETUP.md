# SharePlate — Local Setup

SharePlate is a Django application designed to run locally for the BCA project. SQLite is used by default, so PostgreSQL is not required.

## Requirements

- Python 3.11 or newer
- Git

## Windows

```powershell
cd Shareplate
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/

## macOS / Linux

```bash
cd Shareplate
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/

## Database

The project automatically creates `db.sqlite3` in the project folder. No database server, password or connection string is needed.

## Useful commands

```bash
python manage.py check
python manage.py test core
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

Do not commit `db.sqlite3`, the `venv` folder, or uploaded media containing real personal data.