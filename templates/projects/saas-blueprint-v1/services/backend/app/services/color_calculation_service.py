"""
ColorCalculationService
=======================
Calcula on-colors, gradientes e variantes WCAG (regular / AA / AAA)
para o sistema de cores multi-tenant.

Tradução 1:1 das funções JS do docs/reference/color-settings.html.
"""
import math
from typing import Dict


class ColorCalculationService:
    # ── Primitivas WCAG ───────────────────────────────────────────────────────

    def calculate_luminance(self, hex_color: str) -> float:
        """Luminância WCAG 2.1."""
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
        def lin(c): return c / 12.92 if c <= 0.03928 else math.pow((c + 0.055) / 1.055, 2.4)
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    def calculate_contrast_ratio(self, c1: str, c2: str) -> float:
        l1, l2 = self.calculate_luminance(c1), self.calculate_luminance(c2)
        bright, dark = max(l1, l2), min(l1, l2)
        return (bright + 0.05) / (dark + 0.05)

    def pick_on_color(self, bg: str, threshold: float = 0.5) -> str:
        """Retorna #FFFFFF ou #000000 conforme luminância do fundo."""
        return "#FFFFFF" if self.calculate_luminance(bg) < threshold else "#000000"

    def pick_gradient_on_color(self, ca: str, cb: str, threshold: float = 0.5) -> str:
        """on-color para gradiente entre duas cores.

        Se on(a) == on(b), retorna esse; caso contrário, usa média de luminância.
        """
        oa = self.pick_on_color(ca, threshold)
        ob = self.pick_on_color(cb, threshold)
        if oa == ob:
            return oa
        avg = (self.calculate_luminance(ca) + self.calculate_luminance(cb)) / 2
        return "#FFFFFF" if avg < threshold else "#000000"

    # ── Variantes WCAG ────────────────────────────────────────────────────────

    def apply_accessibility_enhancement(self, hex_color: str, level: str) -> str:
        """Aplica darken conforme nível WCAG: regular=original | AA=-5% | AAA=-10%."""
        if level == "regular":
            return hex_color.upper()
        factor = 0.05 if level == "AA" else 0.10
        h = hex_color.lstrip("#")
        r, g, b = (max(0, round(int(h[i:i+2], 16) * (1 - factor))) for i in (0, 2, 4))
        return "#" + "".join(f"{v:02X}" for v in (r, g, b))

    def calculate_all_variants(self, base_colors: Dict[str, str], threshold: float = 0.5) -> Dict[str, str]:
        """Calcula on_color1..5 e on_gradient_1_2..5_1 a partir das 5 cores base."""
        result = dict(base_colors)
        for n in range(1, 6):
            result[f"on_color{n}"] = self.pick_on_color(base_colors[f"color{n}"], threshold)
        pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1)]
        for a, b in pairs:
            result[f"on_gradient_{a}_{b}"] = self.pick_gradient_on_color(
                base_colors[f"color{a}"], base_colors[f"color{b}"], threshold
            )
        return result

    def build_level(self, base_colors: Dict[str, str], level: str, threshold: float = 0.5) -> Dict[str, str]:
        """Gera um objeto completo para um nível WCAG (após aplicar darken)."""
        enhanced = {
            f"color{n}": self.apply_accessibility_enhancement(base_colors[f"color{n}"], level)
            for n in range(1, 6)
        }
        return {"accessibility_level": level, **self.calculate_all_variants(enhanced, threshold)}

    def build_all_levels(
        self,
        base_colors: Dict[str, str],
        schema_mode: str,
        theme_mode: str,
        threshold: float = 0.5,
    ) -> list[Dict[str, str]]:
        """Gera os 3 níveis WCAG (regular, AA, AAA) para um conjunto de 5 cores."""
        result = []
        for level in ("regular", "AA", "AAA"):
            row = self.build_level(base_colors, level, threshold)
            row["color_schema_mode"] = schema_mode
            row["theme_mode"] = theme_mode
            result.append(row)
        return result
