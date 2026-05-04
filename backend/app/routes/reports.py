from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.organization import Organization, OrganizationMember
from app.models.cost import CostRecord
from app.models.security import ThreatDetection
from io import BytesIO, StringIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
import pandas as pd
reports_bp = Blueprint('reports', __name__)


def infer_plan(max_resources):
    if max_resources is None:
        return 'starter'
    if max_resources >= 200:
        return 'enterprise'
    if max_resources >= 100:
        return 'pro'
    return 'starter'


@reports_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_report():
    """Generate PDF report."""
    user_id = get_jwt_identity()
    data = request.get_json()
    org_id = data.get('organization_id')
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    report_type = data.get('report_type', 'summary')
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    # Title
    title = Paragraph(
        f"Cloud Policy, Cost & Security Simulator - {report_type.title()} Report",
        styles['Heading1']
    )
    story.append(title)
    story.append(Spacer(1, 12))
    # Date
    date_para = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal'])
    story.append(date_para)
    story.append(Spacer(1, 12))
    org = Organization.query.get(org_id)
    if report_type == 'summary':
        summary_rows = [
            ['Organization', org.name if org else f'Organization #{org_id}'],
            ['Plan', infer_plan(org.max_resources) if org else 'starter'],
            ['Member Count', str(len(org.members)) if org else '0'],
            ['Resource Count', str((len(org.resources) + len(org.databases)) if org else 0)],
            ['Active Threats', str(ThreatDetection.query.filter_by(organization_id=org_id, status='active').count())],
            ['Current Month Spend', f"${sum(c.total_cost for c in CostRecord.query.filter_by(organization_id=org_id).all()):.2f}"],
        ]
        summary_table = Table([['Metric', 'Value']] + summary_rows)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            'This report summarizes the simulator status, cost posture, and threat activity for the selected organization.',
            styles['BodyText']
        ))
    elif report_type == 'cost':
        # Cost summary table
        costs = CostRecord.query.filter_by(organization_id=org_id).all()
        cost_data = [['Date', 'Service', 'Amount']] + \
                   [[str(c.date), c.resource_type, f"${c.total_cost:.2f}"] for c in costs[-50:]]
        table = Table(cost_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
    elif report_type == 'security':
        threats = ThreatDetection.query.filter_by(organization_id=org_id).all()
        threat_data = [['Date', 'Type', 'Severity', 'Status']] + \
                     [[t.detected_at.strftime('%Y-%m-%d'), 
                       t.threat_type.value if t.threat_type else 'unknown',
                       t.severity.value if t.severity else 'unknown',
                       t.status] for t in threats]
        table = Table(threat_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.red),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{report_type}_report_{datetime.now().strftime("%Y%m%d")}.pdf'
    )
@reports_bp.route('/export/csv', methods=['GET'])
@jwt_required()
def export_csv():
    """Export data as CSV."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    data_type = request.args.get('type', 'costs')
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    if data_type == 'costs':
        data = CostRecord.query.filter_by(organization_id=org_id).all()
        df = pd.DataFrame([{
            'date': c.date,
            'hour': c.hour,
            'resource_id': c.resource_id,
            'resource_type': c.resource_type,
            'total_cost': c.total_cost,
            'compute_cost': c.compute_cost,
            'storage_cost': c.storage_cost,
            'network_cost': c.network_cost
        } for c in data])
    elif data_type == 'security':
        data = ThreatDetection.query.filter_by(organization_id=org_id).all()
        df = pd.DataFrame([{
            'detected_at': t.detected_at,
            'threat_type': t.threat_type.value if t.threat_type else None,
            'severity': t.severity.value if t.severity else None,
            'confidence_score': t.confidence_score,
            'status': t.status
        } for t in data])
    else:
        return jsonify({'error': 'Invalid export type'}), 400
    buffer = BytesIO()
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    buffer.write(csv_buffer.getvalue().encode('utf-8'))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{data_type}_export_{datetime.now().strftime("%Y%m%d")}.csv'
    )
