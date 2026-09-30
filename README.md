# SharePlate

**Good food deserves another table.**

SharePlate connects food partners with verified recipient organizations so safe surplus food can be collected instead of unnecessarily discarded.

## Current implementation

The repository originally used Next.js + Prisma. A simpler **Python + Django + PostgreSQL** implementation is now being developed on the `django-migration` branch.

### Django stack

- Python 3.12+
- Django 5.2
- PostgreSQL
- Django ORM
- Django authentication and sessions
- Django Admin
- Server-rendered templates

### Core workflows

- Organization verification
- Food listings
- Transaction-safe reservations
- Inventory remaining quantity
- Courier pickup workflow
- Collection and delivery quantities
- Pickup status history
- Impact records
- Notifications
- Complaints
- Immutable-style audit records through Django Admin read-only fields

### Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Set `DATABASE_URL` to your PostgreSQL database. Do not commit `.env` or production secrets.

## Food-safety note

SharePlate provides operational information and does not guarantee food safety. Food providers remain responsible for complying with applicable food-safety requirements.
