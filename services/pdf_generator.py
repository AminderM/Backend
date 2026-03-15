"""
Invoice PDF Generator - Phase 5
Professional PDF invoices with Canadian tax compliance
Uses ReportLab for precise layout control
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from datetime import datetime
from typing import Optional, Dict, Any
from io import BytesIO
import os


class InvoicePDFGenerator:
    """Generate professional PDF invoices"""
    
    def __init__(self, company_info: Dict[str, Any] = None):
        """
        Initialize with company information
        
        company_info should contain:
        - company_name
        - address_line1, city, province, postal_code
        - phone, email
        - gst_number (GST/HST registration)
        - logo_url (optional)
        """
        self.company_info = company_info or {}
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='InvoiceTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=20,
            alignment=TA_RIGHT
        ))
        
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#1a365d'),
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CompanyAddress',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#4a5568'),
            leading=12
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1a365d'),
            fontName='Helvetica-Bold',
            spaceBefore=10,
            spaceAfter=5
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomerInfo',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#2d3748'),
            leading=14
        ))
        
        self.styles.add(ParagraphStyle(
            name='TaxNumber',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#718096')
        ))
        
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#718096'),
            alignment=TA_CENTER
        ))
    
    def generate_invoice_pdf(self, invoice: Dict[str, Any]) -> BytesIO:
        """
        Generate PDF for an invoice
        
        Returns BytesIO buffer containing the PDF
        """
        buffer = BytesIO()
        
        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.75*inch
        )
        
        # Build content
        elements = []
        
        # Header section
        elements.extend(self._build_header(invoice))
        
        # Bill To section
        elements.extend(self._build_bill_to(invoice))
        
        # Invoice details (number, date, due date)
        elements.extend(self._build_invoice_details(invoice))
        
        # Line items table
        elements.extend(self._build_line_items_table(invoice))
        
        # Totals section
        elements.extend(self._build_totals(invoice))
        
        # Notes section
        if invoice.get('notes'):
            elements.extend(self._build_notes(invoice))
        
        # Terms section
        if invoice.get('terms_and_conditions'):
            elements.extend(self._build_terms(invoice))
        
        # Footer
        elements.extend(self._build_footer(invoice))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return buffer
    
    def _build_header(self, invoice: Dict[str, Any]) -> list:
        """Build header with company info and invoice title"""
        elements = []
        
        # Create header table (company info on left, INVOICE on right)
        company_name = self.company_info.get('company_name', 'Your Company Name')
        address = self.company_info.get('address_line1', '')
        city_prov = f"{self.company_info.get('city', '')}, {self.company_info.get('province', '')} {self.company_info.get('postal_code', '')}"
        phone = self.company_info.get('phone', '')
        email = self.company_info.get('email', '')
        
        company_text = f"""
        <b>{company_name}</b><br/>
        {address}<br/>
        {city_prov}<br/>
        {phone}<br/>
        {email}
        """
        
        # GST/HST number
        gst_text = ""
        if self.company_info.get('gst_number'):
            gst_text = f"GST/HST #: {self.company_info.get('gst_number')}"
        if self.company_info.get('qst_number'):
            gst_text += f"<br/>QST #: {self.company_info.get('qst_number')}"
        
        header_data = [
            [
                Paragraph(company_text.strip(), self.styles['CompanyAddress']),
                Paragraph("INVOICE", self.styles['InvoiceTitle'])
            ]
        ]
        
        header_table = Table(header_data, colWidths=[4*inch, 3.5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        
        elements.append(header_table)
        
        if gst_text:
            elements.append(Paragraph(gst_text, self.styles['TaxNumber']))
        
        elements.append(Spacer(1, 20))
        
        return elements
    
    def _build_bill_to(self, invoice: Dict[str, Any]) -> list:
        """Build Bill To section"""
        elements = []
        
        # Bill To header
        elements.append(Paragraph("BILL TO", self.styles['SectionHeader']))
        
        # Customer info
        customer_text = f"""
        <b>{invoice.get('customer_name', 'Customer')}</b><br/>
        {invoice.get('billing_address_line1', '')}<br/>
        """
        
        if invoice.get('billing_address_line2'):
            customer_text += f"{invoice.get('billing_address_line2')}<br/>"
        
        customer_text += f"{invoice.get('billing_city', '')}, {invoice.get('billing_province', '')} {invoice.get('billing_postal_code', '')}"
        
        if invoice.get('customer_email'):
            customer_text += f"<br/>{invoice.get('customer_email')}"
        
        elements.append(Paragraph(customer_text.strip(), self.styles['CustomerInfo']))
        elements.append(Spacer(1, 15))
        
        return elements
    
    def _build_invoice_details(self, invoice: Dict[str, Any]) -> list:
        """Build invoice number, date, due date section"""
        elements = []
        
        # Invoice details in a small table on the right
        details_data = [
            ["Invoice Number:", invoice.get('invoice_number', '')],
            ["Invoice Date:", self._format_date(invoice.get('invoice_date'))],
            ["Due Date:", self._format_date(invoice.get('due_date'))],
            ["Currency:", invoice.get('currency', 'CAD')],
        ]
        
        if invoice.get('order_ids'):
            order_count = len(invoice.get('order_ids', []))
            details_data.append(["Orders:", f"{order_count} order(s)"])
        
        details_table = Table(details_data, colWidths=[1.5*inch, 2*inch])
        details_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#2d3748')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        # Wrap in outer table to right-align
        outer_data = [['', details_table]]
        outer_table = Table(outer_data, colWidths=[4*inch, 3.5*inch])
        outer_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        
        elements.append(outer_table)
        elements.append(Spacer(1, 20))
        
        return elements
    
    def _build_line_items_table(self, invoice: Dict[str, Any]) -> list:
        """Build line items table"""
        elements = []
        
        # Table header
        header = ['Description', 'Qty', 'Unit Price', 'Amount']
        
        # Table data
        data = [header]
        
        for item in invoice.get('line_items', []):
            description = item.get('description', '')
            
            # Add route info if available
            if item.get('origin') and item.get('destination'):
                description += f"\n{item.get('origin')} → {item.get('destination')}"
            
            # Add reference numbers
            if item.get('order_number'):
                description += f"\nOrder: {item.get('order_number')}"
            if item.get('pro_number'):
                description += f" | PRO: {item.get('pro_number')}"
            
            row = [
                description,
                f"{item.get('quantity', 1):.2f}",
                f"${item.get('unit_price', 0):,.2f}",
                f"${item.get('line_total', 0):,.2f}"
            ]
            data.append(row)
        
        # Create table
        col_widths = [4.5*inch, 0.75*inch, 1*inch, 1.25*inch]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        
        table.setStyle(TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Body style
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        
        return elements
    
    def _build_totals(self, invoice: Dict[str, Any]) -> list:
        """Build totals section with tax breakdown"""
        elements = []
        
        # Build totals data
        totals_data = [
            ["Subtotal:", f"${invoice.get('subtotal', 0):,.2f}"],
        ]
        
        # Add tax lines if applicable
        if not invoice.get('is_tax_exempt'):
            if invoice.get('gst_amount', 0) > 0:
                gst_rate = invoice.get('gst_rate', 5)
                totals_data.append([f"GST ({gst_rate}%):", f"${invoice.get('gst_amount', 0):,.2f}"])
            
            if invoice.get('pst_amount', 0) > 0:
                pst_rate = invoice.get('pst_rate', 0)
                totals_data.append([f"PST ({pst_rate}%):", f"${invoice.get('pst_amount', 0):,.2f}"])
            
            if invoice.get('hst_amount', 0) > 0:
                hst_rate = invoice.get('hst_rate', 0)
                totals_data.append([f"HST ({hst_rate}%):", f"${invoice.get('hst_amount', 0):,.2f}"])
            
            if invoice.get('qst_amount', 0) > 0:
                qst_rate = invoice.get('qst_rate', 0)
                totals_data.append([f"QST ({qst_rate}%):", f"${invoice.get('qst_amount', 0):,.2f}"])
            
            if invoice.get('total_tax', 0) > 0:
                totals_data.append(["Total Tax:", f"${invoice.get('total_tax', 0):,.2f}"])
        else:
            totals_data.append(["Tax:", "EXEMPT"])
        
        totals_data.append(["", ""])  # Separator
        totals_data.append(["TOTAL:", f"${invoice.get('grand_total', 0):,.2f}"])
        
        # Payment info if applicable
        if invoice.get('amount_paid', 0) > 0:
            totals_data.append(["Payments Received:", f"-${invoice.get('amount_paid', 0):,.2f}"])
            totals_data.append(["BALANCE DUE:", f"${invoice.get('balance_due', 0):,.2f}"])
        
        # Create totals table (right-aligned)
        totals_table = Table(totals_data, colWidths=[1.5*inch, 1.5*inch])
        totals_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2d3748')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            
            # Grand total highlight
            ('FONTSIZE', (0, -3), (-1, -3), 12),
            ('FONTNAME', (0, -3), (-1, -3), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, -3), (-1, -3), colors.HexColor('#1a365d')),
            ('LINEABOVE', (0, -3), (-1, -3), 1, colors.HexColor('#1a365d')),
            ('TOPPADDING', (0, -3), (-1, -3), 8),
            
            # Balance due highlight if present
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        
        # Wrap to right-align
        outer_data = [['', totals_table]]
        outer_table = Table(outer_data, colWidths=[4.5*inch, 3*inch])
        outer_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        
        elements.append(outer_table)
        elements.append(Spacer(1, 20))
        
        return elements
    
    def _build_notes(self, invoice: Dict[str, Any]) -> list:
        """Build notes section"""
        elements = []
        
        elements.append(Paragraph("Notes", self.styles['SectionHeader']))
        elements.append(Paragraph(invoice.get('notes', ''), self.styles['Normal']))
        elements.append(Spacer(1, 10))
        
        return elements
    
    def _build_terms(self, invoice: Dict[str, Any]) -> list:
        """Build terms and conditions section"""
        elements = []
        
        elements.append(Paragraph("Terms & Conditions", self.styles['SectionHeader']))
        terms_style = ParagraphStyle(
            name='Terms',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#718096')
        )
        elements.append(Paragraph(invoice.get('terms_and_conditions', ''), terms_style))
        elements.append(Spacer(1, 10))
        
        return elements
    
    def _build_footer(self, invoice: Dict[str, Any]) -> list:
        """Build footer section"""
        elements = []
        
        # Payment instructions
        payment_text = "Payment Methods: Bank Transfer (EFT), Cheque, Interac e-Transfer"
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(payment_text, self.styles['Footer']))
        
        # Thank you message
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Thank you for your business!", self.styles['Footer']))
        
        return elements
    
    def _format_date(self, date_value) -> str:
        """Format date for display"""
        if not date_value:
            return ""
        
        if isinstance(date_value, str):
            try:
                from datetime import date
                date_value = date.fromisoformat(date_value)
            except ValueError:
                return date_value
        
        return date_value.strftime("%B %d, %Y")


def generate_invoice_pdf(invoice: Dict[str, Any], company_info: Dict[str, Any] = None) -> BytesIO:
    """
    Convenience function to generate invoice PDF
    
    Args:
        invoice: Invoice data dictionary
        company_info: Company billing information
    
    Returns:
        BytesIO buffer containing PDF
    """
    generator = InvoicePDFGenerator(company_info)
    return generator.generate_invoice_pdf(invoice)
