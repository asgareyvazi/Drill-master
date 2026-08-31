"""Canonical mud volume balance and related mixing calculations.

final = opening_active + additions + transfers_in + returns
        − losses − transfers_out − dumped

Dilution water is an addition (increases volume, decreases MW) and is
tracked separately so the UI can show it without a second formula.
"""
from __future__ import annotations

from typing import List, Optional

from ..result import (
    EngineeringResult,
    MissingInputError,
    EngineeringError,
    ok,
    missing,
    failed,
    require_number,
    optional_number,
)


class MudVolumeEngine:
    METHOD = "Mass/volume balance; no hidden defaults"
    SCOPE = "COMPLETE"

    @classmethod
    def balance(
        cls,
        active_volume_bbl,
        additions_bbl=0,
        losses_bbl=0,
        transfers_in_bbl=0,
        transfers_out_bbl=0,
        returns_bbl=0,
        dilution_bbl=0,
        dumped_bbl=0,
    ) -> EngineeringResult:
        try:
            active = require_number(active_volume_bbl, "active_volume_bbl")
            add = require_number(additions_bbl, "additions_bbl") if additions_bbl not in (None, "") else 0.0
            loss = require_number(losses_bbl, "losses_bbl") if losses_bbl not in (None, "") else 0.0
            tin = require_number(transfers_in_bbl, "transfers_in_bbl") if transfers_in_bbl not in (None, "") else 0.0
            tout = require_number(transfers_out_bbl, "transfers_out_bbl") if transfers_out_bbl not in (None, "") else 0.0
            ret = require_number(returns_bbl, "returns_bbl") if returns_bbl not in (None, "") else 0.0
            dil = require_number(dilution_bbl, "dilution_bbl") if dilution_bbl not in (None, "") else 0.0
            dump = require_number(dumped_bbl, "dumped_bbl") if dumped_bbl not in (None, "") else 0.0
            for name, val in [
                ("active_volume_bbl", active),
                ("additions_bbl", add),
                ("losses_bbl", loss),
                ("transfers_in_bbl", tin),
                ("transfers_out_bbl", tout),
                ("returns_bbl", ret),
                ("dilution_bbl", dil),
                ("dumped_bbl", dump),
            ]:
                if val < 0:
                    raise EngineeringError(f"{name} cannot be negative")

            # Dilution is water added to the system: it increases final volume.
            final = active + add + tin + ret + dil - loss - tout - dump
            warnings: List[str] = []
            if final < 0:
                warnings.append("Final volume is negative — check losses/transfers/dump")
            values = {
                "active_volume_bbl": active,
                "additions_bbl": add,
                "losses_bbl": loss,
                "transfers_in_bbl": tin,
                "transfers_out_bbl": tout,
                "returns_bbl": ret,
                "dilution_bbl": dil,
                "dumped_bbl": dump,
                "final_volume_bbl": round(final, 3),
                "net_change_bbl": round(final - active, 3),
            }
            return ok(
                round(final, 3),
                values=values,
                unit="bbl",
                formula="final = active + additions + transfers_in + returns + dilution − losses − transfers_out − dumped",
                method=cls.METHOD,
                assumptions=[
                    "Volumes in the same unit (bbl)",
                    "Dilution is added water (volume up); dumped is discarded mud",
                    "No compressibility / temperature correction",
                ],
                warnings=warnings,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def weight_up(cls, current_mw, target_mw, system_vol, additive_density) -> EngineeringResult:
        """Sacks of weighting agent. Densities and volume must share a consistent unit set.

        When MW and additive density are in pcf and volume in bbl:
          sacks = V×42×(target−current)/(ρ_add−target)/100   (100 lb sacks)
        """
        try:
            cur = require_number(current_mw, "current_mw")
            tgt = require_number(target_mw, "target_mw")
            vol = require_number(system_vol, "system_vol")
            rho = require_number(additive_density, "additive_density")
            if tgt <= cur:
                raise EngineeringError("Target MW must be > current MW")
            if rho <= tgt:
                raise EngineeringError("Additive density must be > target MW")
            if vol <= 0:
                raise EngineeringError("System volume must be > 0")
            sacks = vol * 42.0 * (tgt - cur) / (rho - tgt) / 100.0
            vol_inc = sacks * 100.0 / rho * 7.4805 / 42.0
            values = {
                "sacks": round(sacks, 2),
                "volume_increase_bbl": round(vol_inc, 3),
                "final_volume_bbl": round(vol + vol_inc, 3),
            }
            return ok(
                round(sacks, 2),
                values=values,
                unit="sacks",
                formula="sacks = V×42×(MW2−MW1)/(ρ_add−MW2)/100",
                method="Material balance, 100-lb sacks",
                assumptions=["MW and additive density in the same density unit (typically pcf)"],
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def dilution(cls, current_mw, target_mw, system_vol, dilutant_mw) -> EngineeringResult:
        try:
            cur = require_number(current_mw, "current_mw")
            tgt = require_number(target_mw, "target_mw")
            vol = require_number(system_vol, "system_vol")
            dil = require_number(dilutant_mw, "dilutant_mw")
            if tgt >= cur:
                raise EngineeringError("Target MW must be < current MW for dilution")
            if tgt <= dil:
                raise EngineeringError("Target MW must be > dilutant MW")
            if vol <= 0:
                raise EngineeringError("System volume must be > 0")
            water = vol * (cur - tgt) / (tgt - dil)
            values = {
                "water_required_bbl": round(water, 3),
                "final_volume_bbl": round(vol + water, 3),
            }
            return ok(
                round(water, 3),
                values=values,
                unit="bbl",
                formula="V_water = V × (MW1−MW2)/(MW2−MW_dilutant)",
                method="Material balance",
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def mix(cls, mw1, vol1, mw2, vol2) -> EngineeringResult:
        try:
            a = require_number(mw1, "mw1")
            va = require_number(vol1, "vol1")
            b = require_number(mw2, "mw2")
            vb = require_number(vol2, "vol2")
            tot = va + vb
            if tot <= 0:
                raise EngineeringError("Total volume must be > 0")
            final = (a * va + b * vb) / tot
            values = {"final_mw": round(final, 4), "total_volume": round(tot, 3)}
            return ok(
                round(final, 4),
                values=values,
                unit="density unit of inputs",
                formula="MW_mix = (MW1×V1 + MW2×V2)/(V1+V2)",
                method="Volume-weighted mix",
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
