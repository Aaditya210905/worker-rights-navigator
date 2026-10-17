"""
wage_calculator.py -- Salary and Unpaid-Wage Calculator for Indian Workers.

Implements statutory wage claim logic under:
1. The Code on Wages, 2019 (Act No. 29 of 2019):
   - Section 18: Permissible deductions and the 50% statutory deduction cap.
   - Section 43: Responsibility for payment of wages.
   - Section 45: Claims arising out of deductions or delay, providing up to 10x compensation.
2. The Payment of Wages Act, 1936 (principles preserved in Code on Wages).
3. State Minimum Wage & Floor Wage benchmarks for informal & gig workers.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.case.models import WorkerType, IndianState


# Indicative monthly minimum wage floor benchmarks by state (for unskilled/semi-skilled informal workers)
STATE_MINIMUM_WAGE_BENCHMARKS = {
    IndianState.DELHI.value: 18066,
    IndianState.KARNATAKA.value: 16500,
    IndianState.MAHARASHTRA.value: 15800,
    IndianState.TAMIL_NADU.value: 14500,
    IndianState.TELANGANA.value: 15200,
    IndianState.RAJASTHAN.value: 13800,
    IndianState.UTTAR_PRADESH.value: 12500,
    IndianState.BIHAR.value: 11800,
    IndianState.WEST_BENGAL.value: 12200,
}
DEFAULT_FLOOR_WAGE = 14000  # National indicative floor benchmark


class WageLineItem(BaseModel):
    category: str  # "base_pay", "incentive", "unlawful_deduction", "expense"
    description: str
    amount: float
    is_claimable: bool = True
    legal_note: str


class WageCalculationResult(BaseModel):
    currency: str = "INR"
    base_unpaid: float
    withheld_incentives: float
    unauthorized_deductions: float
    fuel_or_expenses_withheld: float
    net_unpaid_balance: float
    statutory_compensation_estimate: float  # Up to 10x of withheld under Sec 45
    total_statutory_claim_amount: float     # Balance + statutory compensation
    deduction_cap_violation: bool           # True if deductions exceed 50%
    state_benchmark_monthly: float
    itemized_breakdown: List[WageLineItem]
    legal_citations: List[str]
    claim_summary_en: str
    claim_summary_hi: str

    def to_annexure_markdown(self) -> str:
        """Generates formatted Markdown calculation sheet for complaint annexure."""
        rows = [
            "### Itemized Wage Claim Calculation Sheet",
            f"**Statutory Reference:** Code on Wages, 2019 (Sections 18 & 45)\n",
            "| Component | Description | Amount (₹) | Legal Classification |",
            "| :--- | :--- | :---: | :--- |",
        ]
        for item in self.itemized_breakdown:
            rows.append(f"| {item.category.replace('_', ' ').title()} | {item.description} | ₹{item.amount:,.2f} | {item.legal_note} |")

        rows.extend([
            "| **Total Unpaid Wages Due** | **Net Principal Owed** | **₹" + f"{self.net_unpaid_balance:,.2f}" + "** | **Section 43/45 Code on Wages** |",
            "| Statutory Compensation (Sec 45) | Exemplary damages (up to 10x claimable) | ₹" + f"{self.statutory_compensation_estimate:,.2f}" + " | Section 45(2) Code on Wages |",
            "| **Total Formal Claim Demand** | **Principal + Statutory Relief** | **₹" + f"{self.total_statutory_claim_amount:,.2f}" + "** | **Total Demand** |",
        ])
        if self.deduction_cap_violation:
            rows.append("\n> ⚠️ **Statutory Alert:** Platform deductions exceed the 50% statutory maximum under Section 18(3) of the Code on Wages, 2019.")
        return "\n".join(rows)


class WageCalculator:
    """
    Computes unpaid wage claims, unauthorized deduction violations,
    and statutory compensation under Indian Labour Law.
    """

    @classmethod
    def calculate(
        cls,
        base_unpaid: float = 0.0,
        withheld_incentives: float = 0.0,
        unauthorized_deductions: float = 0.0,
        fuel_or_expenses_withheld: float = 0.0,
        worker_type: WorkerType | str = WorkerType.GIG_WORKER,
        state: IndianState | str = IndianState.UNKNOWN,
        period_description: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> WageCalculationResult:
        """
        Runs calculation and generates statutory breakdown.
        """
        base = max(0.0, float(base_unpaid or 0.0))
        incentives = max(0.0, float(withheld_incentives or 0.0))
        deductions = max(0.0, float(unauthorized_deductions or 0.0))
        expenses = max(0.0, float(fuel_or_expenses_withheld or 0.0))

        net_principal = base + incentives + deductions + expenses

        # Statutory compensation under Section 45, Code on Wages:
        # Authority can award compensation up to 10 times the amount of wages delayed or wrongfully deducted.
        # For dispute notices, we claim 2x to 5x standard exemplary compensation.
        statutory_compensation = round(net_principal * 3.0, 2) if net_principal > 0 else 0.0
        total_statutory_claim = round(net_principal + statutory_compensation, 2)

        # Check Section 18(3) violation: Total deductions cannot exceed 50% of wages
        total_gross_earnings = base + incentives + expenses
        deduction_ratio = deductions / (total_gross_earnings + deductions) if (total_gross_earnings + deductions) > 0 else 0.0
        deduction_cap_violation = (deduction_ratio > 0.50) or (deductions > 0 and total_gross_earnings == 0)


        # State benchmark
        state_key = state.value if hasattr(state, "value") else str(state)
        benchmark = STATE_MINIMUM_WAGE_BENCHMARKS.get(state_key, DEFAULT_FLOOR_WAGE)

        items: List[WageLineItem] = []

        if base > 0:
            items.append(WageLineItem(
                category="base_pay",
                description=f"Unpaid earnings / trip fares ({period_description or 'disputed period'})",
                amount=base,
                is_claimable=True,
                legal_note="Statutory earned wage under Section 43, Code on Wages, 2019",
            ))

        if incentives > 0:
            items.append(WageLineItem(
                category="incentive",
                description="Withheld surge / performance incentives",
                amount=incentives,
                is_claimable=True,
                legal_note="Contractual wage component under Section 2(y), Code on Wages, 2019",
            ))

        if deductions > 0:
            note = (
                "Unlawful deduction: exceeds Section 18(3) 50% cap & lacks hearing"
                if deduction_cap_violation
                else "Unlawful deduction under Section 18, Code on Wages, 2019"
            )
            items.append(WageLineItem(
                category="unlawful_deduction",
                description="Arbitrary penalty / cancellation fee / uniform deduction",
                amount=deductions,
                is_claimable=True,
                legal_note=note,
            ))

        if expenses > 0:
            items.append(WageLineItem(
                category="expense",
                description="Fuel allowance / vehicle allowance / operational out-of-pocket expenses",
                amount=expenses,
                is_claimable=True,
                legal_note="Reimbursable operational expense under service terms",
            ))

        citations = [
            "Code on Wages, 2019 — Section 18 (Deductions which may be made from wages)",
            "Code on Wages, 2019 — Section 43 (Responsibility for payment of wages)",
            "Code on Wages, 2019 — Section 45 (Claims and Compensation up to 10x)",
        ]

        summary_en = (
            f"Total unpaid amount due is ₹{net_principal:,.2f} (comprising ₹{base:,.2f} base wages, "
            f"₹{incentives:,.2f} withheld incentives, and ₹{deductions:,.2f} unlawful deductions). "
            f"Under Section 45 of the Code on Wages, 2019, you are entitled to claim the principal amount "
            f"plus exemplary compensation up to 10x (estimated formal claim: ₹{total_statutory_claim:,.2f})."
        )

        summary_hi = (
            f"कुल बकाया राशि ₹{net_principal:,.2f} है (जिसमें मूल वेतन ₹{base:,.2f}, रोके गए प्रोत्साहन ₹{incentives:,.2f}, "
            f"तथा गैर-कानूनी कटौती ₹{deductions:,.2f} शामिल हैं)। वेतन संहिता, 2019 की धारा 45 के तहत आप मूल राशि के साथ "
            f"10 गुना तक वैधानिक मुआवजे की मांग कर सकते हैं (कुल मांग: ₹{total_statutory_claim:,.2f})।"
        )

        return WageCalculationResult(
            currency="INR",
            base_unpaid=base,
            withheld_incentives=incentives,
            unauthorized_deductions=deductions,
            fuel_or_expenses_withheld=expenses,
            net_unpaid_balance=net_principal,
            statutory_compensation_estimate=statutory_compensation,
            total_statutory_claim_amount=total_statutory_claim,
            deduction_cap_violation=deduction_cap_violation,
            state_benchmark_monthly=benchmark,
            itemized_breakdown=items,
            legal_citations=citations,
            claim_summary_en=summary_en,
            claim_summary_hi=summary_hi,
        )
