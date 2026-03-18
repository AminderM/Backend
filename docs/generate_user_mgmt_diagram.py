"""
Generate User Management Structure Diagram
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics import renderPDF
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.graphics.charts.piecharts import Pie

def generate_user_management_diagram():
    doc = SimpleDocTemplate(
        "/app/docs/USER_MANAGEMENT_STRUCTURE.pdf",
        pagesize=landscape(letter),
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Title1', parent=styles['Heading1'], fontSize=24, alignment=TA_CENTER, textColor=colors.HexColor('#1a365d')))
    styles.add(ParagraphStyle(name='Heading2Custom', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2c5282')))
    styles.add(ParagraphStyle(name='IssueText', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#c53030'), backColor=colors.HexColor('#fff5f5')))
    styles.add(ParagraphStyle(name='SolutionText', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#276749'), backColor=colors.HexColor('#f0fff4')))
    
    story = []
    
    # Title
    story.append(Paragraph("TMS User Management Structure", styles['Title1']))
    story.append(Spacer(1, 20))
    
    # =====================================================
    # ROLE HIERARCHY TABLE
    # =====================================================
    story.append(Paragraph("1. Current Role Hierarchy", styles['Heading2Custom']))
    story.append(Spacer(1, 10))
    
    role_data = [
        ["Level", "Role", "Description", "Workspace Access"],
        ["1", "PLATFORM_ADMIN", "SAAS Owner - Cross-tenant access", "ALL (Platform-wide)"],
        ["2", "ADMIN", "Company Admin - Full tenant access", "ALL within tenant"],
        ["3", "MANAGER", "Department Head", "ALL within tenant (inherited)"],
        ["4", "DISPATCHER", "Operations - Load management", "Dispatch Operations ONLY"],
        ["4", "BILLING", "Finance - Invoicing, AR/AP", "Accounting ONLY"],
        ["5", "DRIVER", "Mobile app - Load execution", "Driver App ONLY"],
        ["6", "VIEWER", "Read-only access", "View ONLY (no edit)"],
    ]
    
    role_table = Table(role_data, colWidths=[0.6*inch, 1.8*inch, 2.5*inch, 2.8*inch])
    role_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#fef3c7')),  # Highlight dispatcher
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(role_table)
    story.append(Spacer(1, 20))
    
    # =====================================================
    # WORKSPACE MAPPING (THE PROBLEM)
    # =====================================================
    story.append(Paragraph("2. Workspace → Role Access Mapping", styles['Heading2Custom']))
    story.append(Spacer(1, 10))
    
    workspace_data = [
        ["Workspace", "platform_admin", "admin", "manager", "dispatcher", "billing", "driver", "viewer"],
        ["Dispatch Operations", "✓", "✓", "✓", "✓", "✗", "✗", "R"],
        ["Sales / CRM", "✓", "✓", "✓", "✗", "✗", "✗", "R"],
        ["Accounting / Billing", "✓", "✓", "✓", "✗", "✓", "✗", "R"],
        ["HR / User Management", "✓", "✓", "✓", "✗", "✗", "✗", "R"],
        ["Fleet Management", "✓", "✓", "✓", "✓", "✗", "✗", "R"],
        ["Reporting / Analytics", "✓", "✓", "✓", "✗", "✓", "✗", "R"],
        ["Settings / Config", "✓", "✓", "✗", "✗", "✗", "✗", "✗"],
        ["Driver App", "✓", "✓", "✓", "✓", "✗", "✓", "✗"],
    ]
    
    ws_table = Table(workspace_data, colWidths=[1.8*inch, 1*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.8*inch, 0.7*inch, 0.7*inch])
    ws_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#744210')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fffaf0')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ws_table)
    story.append(Paragraph("✓ = Full Access | ✗ = No Access | R = Read Only", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # =====================================================
    # THE ISSUE
    # =====================================================
    story.append(Paragraph("3. ⚠️ IDENTIFIED ISSUE", styles['Heading2Custom']))
    story.append(Spacer(1, 10))
    
    issue_text = """
    <b>Problem:</b> Dispatcher role can see ALL workspaces (Dispatch, Sales, Accounting, HR, etc.)<br/><br/>
    <b>Root Cause:</b> The current implementation has <b>role-based API access control</b> but is <b>MISSING workspace-level visibility control</b>.<br/><br/>
    <b>What exists:</b><br/>
    • Role hierarchy checks (is_dispatcher_or_above, require_billing, etc.)<br/>
    • Permission dictionary (DEFAULT_ROLE_PERMISSIONS) - defines WHAT a role can DO<br/>
    • Tenant isolation (check_tenant_access) - limits data to user's company<br/><br/>
    <b>What's MISSING:</b><br/>
    • <b>Workspace visibility mapping</b> - defines WHICH workspaces/modules a role can SEE<br/>
    • <b>Frontend menu filtering</b> - based on role's allowed workspaces<br/>
    • <b>Module-level access control</b> - beyond just API-level permissions
    """
    story.append(Paragraph(issue_text, styles['IssueText']))
    story.append(Spacer(1, 20))
    
    # =====================================================
    # THE SOLUTION
    # =====================================================
    story.append(Paragraph("4. ✅ RECOMMENDED SOLUTION", styles['Heading2Custom']))
    story.append(Spacer(1, 10))
    
    solution_text = """
    <b>Add Workspace Access Control:</b><br/><br/>
    1. <b>Define WORKSPACE_ACCESS_MAP</b> in models_user.py - maps roles to allowed workspaces<br/><br/>
    2. <b>Add /api/auth/workspaces endpoint</b> - returns list of workspaces user can access<br/><br/>
    3. <b>Frontend must call this endpoint</b> on login and filter sidebar/menu items accordingly<br/><br/>
    4. <b>Add workspace guard on routes</b> - backend should validate workspace access on API calls<br/><br/>
    <b>Example Implementation:</b><br/>
    WORKSPACE_ACCESS = {<br/>
    &nbsp;&nbsp;"dispatcher": ["dispatch", "fleet", "driver_app"],<br/>
    &nbsp;&nbsp;"billing": ["accounting", "invoices", "reports"],<br/>
    &nbsp;&nbsp;"driver": ["driver_app"],<br/>
    }
    """
    story.append(Paragraph(solution_text, styles['SolutionText']))
    
    # Page break for visual diagram
    story.append(PageBreak())
    
    # =====================================================
    # CURRENT vs DESIRED STATE
    # =====================================================
    story.append(Paragraph("5. Current State vs Desired State", styles['Heading2Custom']))
    story.append(Spacer(1, 10))
    
    comparison_data = [
        ["Aspect", "Current State ❌", "Desired State ✅"],
        ["Workspace Visibility", "All roles see all workspaces", "Roles see only allowed workspaces"],
        ["Permission Model", "API-level only", "API + Workspace + Module"],
        ["Menu Filtering", "None (shows everything)", "Dynamic based on role"],
        ["Backend Validation", "Role check on endpoints", "Role + Workspace check"],
        ["Data Model", "No workspace field", "workspace_access[] on User"],
    ]
    
    comp_table = Table(comparison_data, colWidths=[2*inch, 3.5*inch, 3.5*inch])
    comp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (1, 1), (1, -1), colors.HexColor('#fed7d7')),
        ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#c6f6d5')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 30))
    
    # =====================================================
    # PERMISSION MATRIX
    # =====================================================
    story.append(Paragraph("6. Current Permission Matrix (DEFAULT_ROLE_PERMISSIONS)", styles['Heading2Custom']))
    story.append(Spacer(1, 10))
    
    perm_data = [
        ["Permission", "platform_admin", "admin", "manager", "dispatcher", "billing", "viewer"],
        ["view_all_tenants", "✓", "", "", "", "", ""],
        ["manage_all_users", "✓", "", "", "", "", ""],
        ["view_tenant_data", "", "✓", "✓", "", "✓", "✓"],
        ["manage_tenant_users", "", "✓", "", "", "", ""],
        ["view_loads", "", "", "", "✓", "", ""],
        ["manage_loads", "", "", "", "✓", "", ""],
        ["view_drivers", "", "", "", "✓", "", ""],
        ["assign_drivers", "", "", "", "✓", "", ""],
        ["view_billing", "✓", "✓", "", "", "✓", ""],
        ["manage_billing", "✓", "✓", "", "", "✓", ""],
        ["view_invoices", "", "", "", "", "✓", ""],
        ["manage_invoices", "", "", "", "", "✓", ""],
    ]
    
    perm_table = Table(perm_data, colWidths=[1.8*inch, 1.1*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.8*inch, 0.8*inch])
    perm_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#553c9a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#faf5ff')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(perm_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("<b>Note:</b> Permissions control WHAT a user can DO, but we need WORKSPACE_ACCESS to control WHAT they can SEE.", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    print("PDF generated: /app/docs/USER_MANAGEMENT_STRUCTURE.pdf")

if __name__ == "__main__":
    generate_user_management_diagram()
