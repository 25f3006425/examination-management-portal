"""
PDF Generator for Examination Management Portal
Generates official, standard-compliant vector PDF result reports.
"""

import io
from datetime import datetime

class ResultPDFBuilder:
    def __init__(self):
        self.stream = []
        self.width = 595  # Standard A4 width in points
        self.height = 842 # Standard A4 height in points

    def text(self, x, y, text, size=10, bold=False, color=(0, 0, 0)):
        font = '/F2' if bold else '/F1'
        r, g, b = color
        clean = (
            str(text)
            .replace('\\', '\\\\')
            .replace('(', '\\(')
            .replace(')', '\\)')
        )
        self.stream.append(f'{r:.2f} {g:.2f} {b:.2f} rg')
        self.stream.append(f'BT {font} {size} Tf {x:.1f} {y:.1f} Td ({clean}) Tj ET')
        self.stream.append('0 0 0 rg')

    def line(self, x1, y1, x2, y2, width=1, color=(0.7, 0.7, 0.7)):
        r, g, b = color
        self.stream.append(f'{r:.2f} {g:.2f} {b:.2f} RG')
        self.stream.append(f'{width} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S')
        self.stream.append('0 0 0 RG')

    def rect(self, x, y, w, h, fill_color=None, border_color=(0.8, 0.8, 0.8), border_width=1):
        if fill_color is not None:
            r, g, b = fill_color
            self.stream.append(f'{r:.2f} {g:.2f} {b:.2f} rg')
            self.stream.append(f'{x:.1f} {y:.1f} {w:.1f} {h:.1f} re f')
            self.stream.append('0 0 0 rg')
        if border_color is not None:
            r, g, b = border_color
            self.stream.append(f'{r:.2f} {g:.2f} {b:.2f} RG')
            self.stream.append(f'{border_width} w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S')
            self.stream.append('0 0 0 RG')

    def build_bytes(self):
        content = '\n'.join(self.stream).encode('latin-1', errors='replace')
        objs = []
        objs.append(b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')
        objs.append(b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n')
        objs.append(
            b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
            b'/Contents 6 0 R /Resources << /Font << '
            b'/F1 4 0 R /F2 5 0 R >> >> >>\nendobj\n'
        )
        objs.append(b'4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n')
        objs.append(b'5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n')
        objs.append(
            f'6 0 obj\n<< /Length {len(content)} >>\nstream\n'.encode('latin-1')
            + content
            + b'\nendstream\nendobj\n'
        )

        out = [b'%PDF-1.4\n']
        xref = [0]
        offset = len(out[0])
        for obj in objs:
            xref.append(offset)
            out.append(obj)
            offset += len(obj)

        startxref = offset
        out.append(f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'.encode('latin-1'))
        for x in xref[1:]:
            out.append(f'{x:010d} 00000 n \n'.encode('latin-1'))
        out.append(
            f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n'.encode(
                'latin-1'
            )
        )
        return b''.join(out)


def generate_result_pdf(evaluation):
    """
    Generates an official result report PDF for an Evaluation object.
    Returns bytes of PDF.
    """
    pdf = ResultPDFBuilder()
    student = evaluation.booking.student
    slot = evaluation.booking.slot
    exam = slot.examination
    course = exam.course
    examiner = evaluation.examiner

    margin_x = 45
    top_y = 800

    # Top Header Banner
    pdf.rect(margin_x, top_y - 45, 505, 50, fill_color=(0.13, 0.22, 0.38), border_color=None)
    pdf.text(margin_x + 15, top_y - 20, "EXAMINATION MANAGEMENT PORTAL", size=14, bold=True, color=(1, 1, 1))
    pdf.text(margin_x + 15, top_y - 36, "Official Academic Evaluation & Grade Report", size=10, bold=False, color=(0.85, 0.9, 0.98))
    pdf.text(margin_x + 360, top_y - 20, f"Ref: EXP-EV-{evaluation.id:05d}", size=9, bold=True, color=(1, 0.84, 0))
    pdf.text(margin_x + 360, top_y - 34, f"Issued: {datetime.now().strftime('%d %b %Y')}", size=8, bold=False, color=(0.8, 0.85, 0.95))

    # Student & Exam Info Boxes
    curr_y = top_y - 60

    # Box 1: Student Information
    pdf.rect(margin_x, curr_y - 80, 245, 80, fill_color=(0.97, 0.98, 1.0), border_color=(0.8, 0.85, 0.92))
    pdf.text(margin_x + 10, curr_y - 18, "STUDENT DETAILS", size=9, bold=True, color=(0.15, 0.25, 0.45))
    pdf.line(margin_x + 10, curr_y - 22, margin_x + 235, curr_y - 22, color=(0.85, 0.88, 0.95))

    roll = student.roll_number if hasattr(student, 'roll_number') and student.roll_number else "N/A"
    dept = student.department if hasattr(student, 'department') and student.department else "General Academic"
    yr = student.year if hasattr(student, 'year') and student.year else "Standard"

    pdf.text(margin_x + 10, curr_y - 36, f"Name: {student.name}", size=9, bold=True)
    pdf.text(margin_x + 10, curr_y - 49, f"Roll Number: {roll}", size=9)
    pdf.text(margin_x + 10, curr_y - 62, f"Department: {dept[:30]}", size=8)
    pdf.text(margin_x + 10, curr_y - 74, f"Year: {yr}  |  Email: {student.email[:25]}", size=8, color=(0.3, 0.3, 0.3))

    # Box 2: Examination Information
    pdf.rect(margin_x + 255, curr_y - 80, 250, 80, fill_color=(0.97, 0.98, 1.0), border_color=(0.8, 0.85, 0.92))
    pdf.text(margin_x + 265, curr_y - 18, "EXAMINATION DETAILS", size=9, bold=True, color=(0.15, 0.25, 0.45))
    pdf.line(margin_x + 265, curr_y - 22, margin_x + 495, curr_y - 22, color=(0.85, 0.88, 0.95))

    pdf.text(margin_x + 265, curr_y - 36, f"Exam: {exam.name[:35]}", size=9, bold=True)
    pdf.text(margin_x + 265, curr_y - 49, f"Course: {course.name[:35]}", size=9)
    pdf.text(margin_x + 265, curr_y - 62, f"Slot Date: {slot.date} at {slot.time}", size=9)
    pdf.text(margin_x + 265, curr_y - 74, f"Evaluated by: {examiner.name}", size=8, color=(0.3, 0.3, 0.3))

    # Rubrics Breakdown Table
    curr_y -= 105
    pdf.text(margin_x, curr_y, "RUBRIC-WISE PERFORMANCE BREAKDOWN", size=10, bold=True, color=(0.15, 0.25, 0.45))
    curr_y -= 8

    # Table Header
    col_w = [30, 295, 90, 90]
    pdf.rect(margin_x, curr_y - 22, 505, 22, fill_color=(0.2, 0.3, 0.5), border_color=None)
    pdf.text(margin_x + 8, curr_y - 15, "Sl.", size=9, bold=True, color=(1, 1, 1))
    pdf.text(margin_x + col_w[0] + 10, curr_y - 15, "Assessment Criterion / Rubric", size=9, bold=True, color=(1, 1, 1))
    pdf.text(margin_x + col_w[0] + col_w[1] + 10, curr_y - 15, "Max Marks", size=9, bold=True, color=(1, 1, 1))
    pdf.text(margin_x + col_w[0] + col_w[1] + col_w[2] + 10, curr_y - 15, "Marks Awarded", size=9, bold=True, color=(1, 1, 1))
    curr_y -= 22

    # Table Rows
    rubric_marks = evaluation.rubric_marks
    total_max = 0
    total_obtained = evaluation.marks or 0

    if rubric_marks:
        for idx, rm in enumerate(rubric_marks, start=1):
            bg = (0.97, 0.98, 0.99) if idx % 2 == 0 else (1.0, 1.0, 1.0)
            row_h = 22
            pdf.rect(margin_x, curr_y - row_h, 505, row_h, fill_color=bg, border_color=(0.9, 0.9, 0.9))
            
            crit_name = rm.rubric.criterion if rm.rubric else f"Criterion #{idx}"
            max_m = rm.rubric.marks if rm.rubric else 0
            total_max += max_m

            pdf.text(margin_x + 8, curr_y - 15, f"{idx}", size=9)
            pdf.text(margin_x + col_w[0] + 10, curr_y - 15, crit_name[:45], size=9)
            pdf.text(margin_x + col_w[0] + col_w[1] + 25, curr_y - 15, str(max_m), size=9)
            pdf.text(margin_x + col_w[0] + col_w[1] + col_w[2] + 25, curr_y - 15, str(rm.marks), size=9, bold=True, color=(0.1, 0.45, 0.2))
            curr_y -= row_h
    else:
        # Fallback if no specific rubric marks recorded
        total_max = sum(r.marks for r in exam.rubrics) if exam.rubrics else 100
        row_h = 22
        pdf.rect(margin_x, curr_y - row_h, 505, row_h, fill_color=(1, 1, 1), border_color=(0.9, 0.9, 0.9))
        pdf.text(margin_x + 8, curr_y - 15, "1", size=9)
        pdf.text(margin_x + col_w[0] + 10, curr_y - 15, "Overall Assessment", size=9)
        pdf.text(margin_x + col_w[0] + col_w[1] + 25, curr_y - 15, str(total_max), size=9)
        pdf.text(margin_x + col_w[0] + col_w[1] + col_w[2] + 25, curr_y - 15, str(total_obtained), size=9, bold=True)
        curr_y -= row_h

    # Table Total Row
    if total_max == 0:
        total_max = 100
    percentage = (total_obtained / total_max * 100) if total_max > 0 else 0

    pdf.rect(margin_x, curr_y - 25, 505, 25, fill_color=(0.92, 0.95, 0.98), border_color=(0.7, 0.8, 0.9), border_width=1.5)
    pdf.text(margin_x + 10, curr_y - 17, "TOTAL AGGREGATE MARKS", size=9, bold=True, color=(0.15, 0.25, 0.45))
    pdf.text(margin_x + col_w[0] + col_w[1] + 25, curr_y - 17, str(total_max), size=10, bold=True)
    pdf.text(margin_x + col_w[0] + col_w[1] + col_w[2] + 25, curr_y - 17, f"{total_obtained}  ({percentage:.1f}%)", size=10, bold=True, color=(0.1, 0.5, 0.2))
    curr_y -= 40

    # Summary & Classification Card
    pdf.rect(margin_x, curr_y - 75, 505, 75, fill_color=(0.98, 0.99, 1.0), border_color=(0.85, 0.88, 0.92))
    
    # Left column of summary: Result Status
    grade_letter = "A+" if percentage >= 90 else ("A" if percentage >= 80 else ("B+" if percentage >= 70 else ("B" if percentage >= 60 else ("C" if percentage >= 50 else "D"))))
    status_text = "PASSED / COMPLETED" if percentage >= 50 else "NEEDS IMPROVEMENT"
    status_color = (0.1, 0.55, 0.25) if percentage >= 50 else (0.8, 0.2, 0.2)

    pdf.text(margin_x + 15, curr_y - 20, "FINAL RESULT:", size=10, bold=True)
    pdf.text(margin_x + 110, curr_y - 20, status_text, size=11, bold=True, color=status_color)
    pdf.text(margin_x + 15, curr_y - 36, f"Grade Equivalent: {grade_letter}  |  Percentage: {percentage:.1f}%", size=9)

    # Remarks
    remarks_str = evaluation.remarks.strip() if evaluation.remarks else "Evaluation completed with satisfactory criteria fulfillment."
    pdf.text(margin_x + 15, curr_y - 54, "Examiner Remarks:", size=8, bold=True, color=(0.3, 0.3, 0.3))
    pdf.text(margin_x + 15, curr_y - 68, f'"{remarks_str[:90]}"', size=9, color=(0.2, 0.2, 0.2))
    curr_y -= 95

    # Sign-off & Verification Footer
    pdf.line(margin_x, curr_y, margin_x + 505, curr_y, color=(0.8, 0.8, 0.8))
    curr_y -= 25

    # Examiner signature placeholder
    pdf.line(margin_x + 330, curr_y, margin_x + 490, curr_y, color=(0.4, 0.4, 0.4))
    pdf.text(margin_x + 355, curr_y - 14, f"Examiner: {examiner.name}", size=8, bold=True)
    pdf.text(margin_x + 355, curr_y - 24, "Authorized Evaluator", size=8, color=(0.5, 0.5, 0.5))

    # Seal / Security Notice
    pdf.text(margin_x, curr_y - 14, "[*] Verified Electronic Examination Record", size=8, bold=True, color=(0.3, 0.4, 0.6))
    pdf.text(margin_x, curr_y - 25, "This is an official system-generated evaluation document.", size=7, color=(0.5, 0.5, 0.5))
    pdf.text(margin_x, curr_y - 34, "Examination Management Portal - Secure Academic Records System", size=7, color=(0.5, 0.5, 0.5))

    return pdf.build_bytes()
