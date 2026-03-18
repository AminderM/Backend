"""
Generate PDF version of API Documentation
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import re

def generate_api_doc_pdf():
    doc = SimpleDocTemplate(
        "/app/docs/API_DOCUMENTATION.pdf",
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    styles.add(ParagraphStyle(
        name='Title1',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=20,
        textColor=colors.HexColor('#1a365d')
    ))
    
    styles.add(ParagraphStyle(
        name='Heading2Custom',
        parent=styles['Heading2'],
        fontSize=16,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor('#2c5282')
    ))
    
    styles.add(ParagraphStyle(
        name='Heading3Custom',
        parent=styles['Heading3'],
        fontSize=12,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#2b6cb0')
    ))
    
    styles.add(ParagraphStyle(
        name='CodeBlock',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=9,
        backColor=colors.HexColor('#f7fafc'),
        leftIndent=10,
        spaceBefore=5,
        spaceAfter=5
    ))
    
    styles.add(ParagraphStyle(
        name='Endpoint',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=10,
        textColor=colors.HexColor('#276749'),
        spaceBefore=10,
        spaceAfter=5
    ))
    
    story = []
    
    # Title Page
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("TMS SAAS API Documentation", styles['Title1']))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("Version 2.0 | March 2026", styles['Normal']))
    story.append(Paragraph("Canada-First Transportation Management System", styles['Normal']))
    story.append(Spacer(1, 1*inch))
    
    # Table of Contents
    toc_data = [
        ["Section", "Description"],
        ["1. Authentication", "Login, JWT tokens, user info"],
        ["2. User Management", "Roles, worker types, permissions"],
        ["3. Master Data", "Carriers, customers, locations, tax calculator"],
        ["4. Orders & Shipments", "Order lifecycle, dispatch, tracking"],
        ["5. Fleet Management", "Vehicles, CVIP inspections, maintenance"],
        ["6. Invoicing", "Invoice creation, PDF, payments, AR reports"],
        ["7. Rate Cards", "Lane pricing, accessorials, rate quotes"],
    ]
    
    toc_table = Table(toc_data, colWidths=[2*inch, 4*inch])
    toc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
    ]))
    story.append(toc_table)
    story.append(PageBreak())
    
    # Section 1: Authentication
    story.append(Paragraph("1. Authentication", styles['Heading2Custom']))
    story.append(Paragraph("All endpoints require JWT Bearer token authentication (except login/register).", styles['Normal']))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Login", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/auth/login", styles['Endpoint']))
    story.append(Paragraph("Request: {\"email\": \"user@example.com\", \"password\": \"password123\"}", styles['CodeBlock']))
    story.append(Paragraph("Response includes: access_token, token_type, user object with role, tenant_id, worker_type", styles['Normal']))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Get Current User", styles['Heading3Custom']))
    story.append(Paragraph("GET /api/auth/me", styles['Endpoint']))
    story.append(Paragraph("Header: Authorization: Bearer &lt;token&gt;", styles['CodeBlock']))
    story.append(PageBreak())
    
    # Section 2: User Management
    story.append(Paragraph("2. User Management & Roles (Phase 1)", styles['Heading2Custom']))
    
    roles_data = [
        ["Role", "Description"],
        ["platform_admin", "SAAS owner, cross-tenant access"],
        ["admin", "Company administrator"],
        ["manager", "Operations manager"],
        ["dispatcher", "Load dispatcher"],
        ["driver", "Driver (mobile app user)"],
        ["billing", "Finance/billing role"],
        ["viewer", "Read-only access"],
    ]
    roles_table = Table(roles_data, colWidths=[2*inch, 4*inch])
    roles_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(Paragraph("User Roles:", styles['Heading3Custom']))
    story.append(roles_table)
    story.append(Spacer(1, 15))
    
    worker_data = [
        ["Worker Type", "Description"],
        ["t4_employee", "T4 Employee (Canadian W2 equivalent)"],
        ["t4a_contractor", "T4A Contractor (Canadian 1099 equivalent)"],
        ["corp_contractor", "Incorporated contractor"],
    ]
    worker_table = Table(worker_data, colWidths=[2*inch, 4*inch])
    worker_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(Paragraph("Worker Types (Canadian Tax):", styles['Heading3Custom']))
    story.append(worker_table)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Endpoints:", styles['Heading3Custom']))
    story.append(Paragraph("GET /api/users - List users (filter by role, status)", styles['Endpoint']))
    story.append(Paragraph("POST /api/users - Create user", styles['Endpoint']))
    story.append(Paragraph("PUT /api/users/{user_id} - Update user", styles['Endpoint']))
    story.append(PageBreak())
    
    # Section 3: Master Data
    story.append(Paragraph("3. Master Data & Tax Calculator (Phase 2)", styles['Heading2Custom']))
    
    story.append(Paragraph("Canadian Tax Calculator", styles['Heading3Custom']))
    story.append(Paragraph("GET /api/master-data/tax/rates - Get all provincial tax rates", styles['Endpoint']))
    story.append(Paragraph("POST /api/master-data/tax/calculate - Calculate tax for amount + province", styles['Endpoint']))
    story.append(Spacer(1, 10))
    
    tax_data = [
        ["Province", "GST", "PST/QST", "HST", "Total"],
        ["AB", "5%", "0%", "0%", "5%"],
        ["BC", "5%", "7%", "0%", "12%"],
        ["ON", "0%", "0%", "13%", "13%"],
        ["QC", "5%", "9.975%", "0%", "14.975%"],
        ["NS/NB/NL/PE", "0%", "0%", "15%", "15%"],
        ["SK", "5%", "6%", "0%", "11%"],
        ["MB", "5%", "7%", "0%", "12%"],
    ]
    tax_table = Table(tax_data, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
    tax_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#276749')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fff4')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Master Data Endpoints:", styles['Heading3Custom']))
    story.append(Paragraph("GET/POST /api/master-data/carriers-brokers - Carriers with NSC, CVOR numbers", styles['Endpoint']))
    story.append(Paragraph("GET/POST /api/master-data/customers - Billable customers", styles['Endpoint']))
    story.append(Paragraph("GET/POST /api/master-data/locations - Warehouses, terminals", styles['Endpoint']))
    story.append(Paragraph("GET/POST /api/master-data/shippers - Pickup parties", styles['Endpoint']))
    story.append(Paragraph("GET/POST /api/master-data/consignees - Delivery parties", styles['Endpoint']))
    story.append(PageBreak())
    
    # Section 4: Orders & Shipments
    story.append(Paragraph("4. Orders & Shipments (Phase 3)", styles['Heading2Custom']))
    
    story.append(Paragraph("Orders (Sales-Facing)", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/operations/orders - Create order with customer rate, tax calc", styles['Endpoint']))
    story.append(Paragraph("GET /api/operations/orders - List orders (filter: status, customer, dates)", styles['Endpoint']))
    story.append(Paragraph("GET /api/operations/orders/{id} - Get order details", styles['Endpoint']))
    story.append(Paragraph("POST /api/operations/orders/{id}/confirm - Confirm order", styles['Endpoint']))
    story.append(Paragraph("POST /api/operations/orders/{id}/cancel - Cancel order", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Shipments (Operations-Facing)", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/operations/shipments - Create shipment from order", styles['Endpoint']))
    story.append(Paragraph("POST /api/operations/shipments/{id}/dispatch - Dispatch to driver", styles['Endpoint']))
    story.append(Paragraph("POST /api/operations/shipments/{id}/status - Update status", styles['Endpoint']))
    story.append(Paragraph("POST /api/operations/shipments/{id}/tracking - Add tracking event", styles['Endpoint']))
    story.append(Spacer(1, 10))
    
    status_data = [
        ["Status", "Description"],
        ["pending", "Created, awaiting dispatch"],
        ["dispatched", "Assigned to driver"],
        ["en_route_pickup", "Driver heading to pickup"],
        ["at_pickup", "Driver at pickup location"],
        ["picked_up", "Loaded, in transit"],
        ["en_route_delivery", "Heading to delivery"],
        ["at_delivery", "At delivery location"],
        ["delivered", "Delivery complete"],
        ["completed", "All paperwork done"],
    ]
    status_table = Table(status_data, colWidths=[2*inch, 4*inch])
    status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(Paragraph("Shipment Statuses:", styles['Heading3Custom']))
    story.append(status_table)
    story.append(PageBreak())
    
    # Section 5: Fleet Management
    story.append(Paragraph("5. Fleet Management (Phase 4)", styles['Heading2Custom']))
    
    story.append(Paragraph("Vehicles", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/fleet/vehicles - Create vehicle (tractor, trailer, straight truck)", styles['Endpoint']))
    story.append(Paragraph("GET /api/fleet/vehicles - List vehicles (filter: type, status)", styles['Endpoint']))
    story.append(Paragraph("GET /api/fleet/vehicles/summary - Fleet summary with compliance alerts", styles['Endpoint']))
    story.append(Paragraph("GET /api/fleet/vehicles/fleet-tracking - Real-time GPS locations", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("CVIP Inspections (Canadian Compliance)", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/fleet/vehicles/{id}/inspections - Add CVIP inspection", styles['Endpoint']))
    story.append(Paragraph("GET /api/fleet/vehicles/{id}/inspections - List inspections", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Maintenance", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/fleet/vehicles/{id}/maintenance - Add maintenance record", styles['Endpoint']))
    story.append(Paragraph("GET /api/fleet/vehicles/{id}/maintenance - List maintenance history", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Driver Assignment & GPS", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/fleet/vehicles/{id}/assign-driver - Assign driver to vehicle", styles['Endpoint']))
    story.append(Paragraph("POST /api/fleet/vehicles/{id}/location - Update GPS location", styles['Endpoint']))
    story.append(PageBreak())
    
    # Section 6: Invoicing
    story.append(Paragraph("6. Invoicing & PDF Generation (Phase 5)", styles['Heading2Custom']))
    
    story.append(Paragraph("Invoices", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/billing/invoices - Create invoice with line items", styles['Endpoint']))
    story.append(Paragraph("POST /api/billing/invoices/from-orders - Create from multiple orders", styles['Endpoint']))
    story.append(Paragraph("GET /api/billing/invoices - List invoices (filter: status, customer, dates)", styles['Endpoint']))
    story.append(Paragraph("POST /api/billing/invoices/{id}/send - Mark as sent", styles['Endpoint']))
    story.append(Paragraph("POST /api/billing/invoices/{id}/cancel - Cancel invoice", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Payments", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/billing/invoices/{id}/payments - Record payment", styles['Endpoint']))
    story.append(Paragraph("GET /api/billing/invoices/{id}/payments - Payment history", styles['Endpoint']))
    story.append(Spacer(1, 10))
    
    payment_data = [
        ["Method", "Description"],
        ["bank_transfer", "Wire/EFT"],
        ["check", "Cheque"],
        ["credit_card", "Credit card"],
        ["interac", "Interac e-Transfer (Canadian)"],
        ["cash", "Cash"],
        ["factoring", "Third-party factoring"],
    ]
    payment_table = Table(payment_data, colWidths=[2*inch, 4*inch])
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#276749')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fff4')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(payment_table)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("PDF Generation", styles['Heading3Custom']))
    story.append(Paragraph("GET /api/billing/invoices/{id}/pdf - Download PDF", styles['Endpoint']))
    story.append(Paragraph("GET /api/billing/invoices/{id}/pdf/preview - Preview PDF in browser", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("AR Reports", styles['Heading3Custom']))
    story.append(Paragraph("GET /api/billing/invoices/reports/ar-summary - AR aging summary", styles['Endpoint']))
    story.append(Paragraph("GET /api/billing/invoices/reports/ar-aging - Detailed aging by customer", styles['Endpoint']))
    story.append(PageBreak())
    
    # Section 7: Rate Cards
    story.append(Paragraph("7. Rate Cards & Accessorials (Phase 6)", styles['Heading2Custom']))
    
    story.append(Paragraph("Accessorial Codes", styles['Heading3Custom']))
    story.append(Paragraph("GET /api/pricing/accessorials/codes - List 25 standard codes", styles['Endpoint']))
    story.append(Paragraph("GET /api/pricing/accessorials/defaults - Default rates", styles['Endpoint']))
    story.append(Paragraph("POST /api/pricing/accessorials - Create/override definition", styles['Endpoint']))
    story.append(Paragraph("GET /api/pricing/accessorials - List tenant definitions", styles['Endpoint']))
    story.append(Spacer(1, 10))
    
    acc_data = [
        ["Code", "Description", "Default Rate"],
        ["det_pickup", "Detention at Pickup", "$75/hr (2hr free)"],
        ["det_delivery", "Detention at Delivery", "$75/hr (2hr free)"],
        ["layover", "Overnight Layover", "$350 flat"],
        ["fuel_surcharge", "Fuel Surcharge", "10% of line haul"],
        ["liftgate", "Liftgate Service", "$75 flat"],
        ["border_crossing", "US/Canada Border", "$200 flat"],
        ["pars_paps", "PARS/PAPS Processing", "$50 flat"],
        ["hazmat", "Hazardous Materials", "$250 flat"],
    ]
    acc_table = Table(acc_data, colWidths=[1.5*inch, 2.5*inch, 1.5*inch])
    acc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#744210')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fffaf0')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(acc_table)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Rate Cards", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/pricing/rate-cards - Create rate card with lane rates", styles['Endpoint']))
    story.append(Paragraph("GET /api/pricing/rate-cards - List rate cards", styles['Endpoint']))
    story.append(Paragraph("GET /api/pricing/rate-cards/{id} - Get rate card details", styles['Endpoint']))
    story.append(Paragraph("PUT /api/pricing/rate-cards/{id} - Update rate card", styles['Endpoint']))
    story.append(Paragraph("POST /api/pricing/rate-cards/{id}/lanes - Add lane rate", styles['Endpoint']))
    story.append(Paragraph("DELETE /api/pricing/rate-cards/{id}/lanes/{lane_id} - Remove lane", styles['Endpoint']))
    story.append(Paragraph("POST /api/pricing/rate-cards/{id}/activate - Activate rate card", styles['Endpoint']))
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Rate Quotes", styles['Heading3Custom']))
    story.append(Paragraph("POST /api/pricing/rate-cards/quote - Calculate rate quote", styles['Endpoint']))
    story.append(Paragraph("Params: origin_city, origin_province, destination_city, destination_province, equipment_type, accessorial_codes", styles['CodeBlock']))
    story.append(Paragraph("GET /api/pricing/rate-cards/lanes/search - Search lanes by corridor", styles['Endpoint']))
    
    # Build PDF
    doc.build(story)
    print("PDF generated successfully: /app/docs/API_DOCUMENTATION.pdf")

if __name__ == "__main__":
    generate_api_doc_pdf()
