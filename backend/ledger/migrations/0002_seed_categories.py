from django.db import migrations

# Splitwise's tree, verbatim, so the history import maps 1:1.
TREE = {
    "Entertainment": ["Games", "Movies", "Music", "Sports", "Other"],
    "Food and drink": ["Dining out", "Groceries", "Liquor", "Other"],
    "Home": [
        "Electronics", "Furniture", "Household supplies", "Maintenance", "Mortgage",
        "Pets", "Rent", "Services", "Other",
    ],
    "Life": [
        "Childcare", "Clothing", "Education", "Gifts", "Insurance",
        "Medical expenses", "Taxes", "Other",
    ],
    "Transportation": [
        "Bicycle", "Bus/train", "Car", "Gas/fuel", "Hotel", "Parking", "Plane", "Taxi", "Other",
    ],
    "Utilities": [
        "Cleaning", "Electricity", "Heat/gas", "Trash", "TV/Phone/Internet", "Water", "Other",
    ],
    "Uncategorized": ["General"],
}


def seed(apps, schema_editor):
    Category = apps.get_model("ledger", "Category")
    for parent_name, children in TREE.items():
        parent, _ = Category.objects.get_or_create(
            parent=None, name=parent_name, defaults={"is_default": True}
        )
        for child in children:
            Category.objects.get_or_create(parent=parent, name=child, defaults={"is_default": True})


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
