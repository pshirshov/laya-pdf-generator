import json
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch

# Load the JSON data from the files
with open('dermatologists.json', 'r') as file:
    derm_data = json.load(file)

with open('approved-hospitals.json', 'r') as file:
    hosp_data = json.load(file)

consultants = derm_data['consultants']
hospitals = hosp_data['hospitals']

# Create a dictionary for quick hospital lookup by id
hospitals_dict = {hosp['id']: hosp for hosp in hospitals}

# Prepare the document in landscape mode
doc = SimpleDocTemplate("dermatologists.pdf", pagesize=landscape(letter))
elements = []

# Styles
styles = getSampleStyleSheet()
title_style = styles['Title']

# Add title
title = Paragraph("List of Dermatology Consultants", title_style)
elements.append(title)
elements.append(Spacer(1, 0.2 * inch))

# Prepare table data
headers = [
    "ID", "Name", "Participating",
    "Speciality Descriptions", "Associated Hospitals"
]

table_data = [headers]

for consultant in consultants:
    # Format associated hospitals with newlines for multiline
    assoc_hospitals = []
    for hid in consultant.get('hospitals', []):
        hosp = hospitals_dict.get(hid)
        if hosp:
            name = hosp.get('name', 'Unknown')
            county = hosp.get('county', 'Unknown')
            phone = hosp.get('phone', 'N/A')
            assoc_hospitals.append(f"{name} ({county}): {phone}")
    assoc_str = '\n'.join(assoc_hospitals)

    row = [
        str(consultant.get('id', '')),
        consultant.get('name', ''),
        consultant.get('participating', ''),
        consultant.get('speciality_descriptions', ''),
        assoc_str
    ]
    table_data.append(row)

# Create the table with adjusted column widths for landscape
# Approx 10 inches usable, redistributed for fewer columns
col_widths = [0.5*inch, 2.0*inch, 0.7*inch, 1.5*inch, 5.3*inch]  # Wider for name and hospitals

table = Table(table_data, colWidths=col_widths)

# Add style to the table
table_style = TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, -1), 8),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black),
    ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
])
table.setStyle(table_style)

elements.append(table)

# Build the PDF
doc.build(elements)

print("PDF generated successfully: dermatologists.pdf")
