# Business glossary: sample database (shop_en.db, English)

This file is sent to the model as business rules. Only lines starting with "- " (and their
continuation lines indented by two spaces) are sent; headings and this note are not.
Write your own copy for your database and pass its path with NL2SQL_GLOSSARY.

- Revenue = quantity * unit_price. Unless asked otherwise, count only orders with status = 'completed' in revenue.
