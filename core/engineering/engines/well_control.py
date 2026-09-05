"""Canonical well-control calculations (IWCF / IADC).

ONE engine for kill MW, MAASP, kick tolerance, trip margin and kick volume.
UI and other tabs must call this module — they must not re-implement formulas.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..result import (
    EngineeringResult,
    MissingInputError,
    EngineeringError,
    ok,
    missing,
    unsupported,
    failed,
    require_number,
    optional_number,
)

PSI_PER_PPG_FT = 0.052


def _result_or_raise(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
    return wrapper


class WellControlEngine:
    """IWCF-aligned well control. No silent defaults for engineering inputs."""

    METHOD = "IWCF / IADC well-control manuals; Bourgoyne et al."

    @staticmethod
    def _frac_mw_ppg(
        shoe_tvd_ft: float,
        frac_mw_ppg=None,
        lot_pressure_psi=None,
        frac_gradient_psi_ft=None,
    ) -> float:
        if frac_mw_ppg not in (None, ""):
            return require_number(frac_mw_ppg, "frac_mw_ppg")
        if lot_pressure_psi not in (None, "") and shoe_tvd_ft > 0:
            return require_number(lot_pressure_psi, "lot_pressure_psi") / (
                PSI_PER_PPG_FT * shoe_tvd_ft
            )
        if frac_gradient_psi_ft not in (None, ""):
            return require_number(frac_gradient_psi_ft, "frac_gradient_psi_ft") / PSI_PER_PPG_FT
        raise MissingInputError("frac_mw_ppg or lot_pressure_psi or frac_gradient_psi_ft")

    @staticmethod
    def _influx_gradient_psi_ft(influx_gradient_psi_ft=None, influx_emw_ppg=None) -> float:
        if influx_gradient_psi_ft not in (None, ""):
            return require_number(influx_gradient_psi_ft, "influx_gradient_psi_ft")
        if influx_emw_ppg not in (None, ""):
            return require_number(influx_emw_ppg, "influx_emw_ppg") * PSI_PER_PPG_FT
        raise MissingInputError("influx_gradient_psi_ft or influx_emw_ppg")

    @staticmethod
    def calculate_kill_mw(original_mw_ppg, sidpp_psi, tvd_ft) -> float:
        mw = require_number(original_mw_ppg, "original_mw_ppg")
        sidpp = require_number(sidpp_psi, "sidpp_psi")
        tvd = require_number(tvd_ft, "tvd_ft")
        if tvd <= 0:
            raise EngineeringError("TVD must be > 0")
        return mw + sidpp / (PSI_PER_PPG_FT * tvd)

    @staticmethod
    def calculate_maasp(
        max_allowable_mw_ppg=None,
        current_mw_ppg=None,
        shoe_tvd_ft=None,
        leak_off_psi=None,
    ) -> float:
        mw = require_number(current_mw_ppg, "current_mw_ppg")
        shoe = require_number(shoe_tvd_ft, "shoe_tvd_ft")
        if shoe <= 0:
            raise EngineeringError("Shoe TVD must be > 0")
        if max_allowable_mw_ppg not in (None, ""):
            frac = require_number(max_allowable_mw_ppg, "max_allowable_mw_ppg")
        elif leak_off_psi not in (None, ""):
            frac = require_number(leak_off_psi, "leak_off_psi") / (PSI_PER_PPG_FT * shoe)
        else:
            raise MissingInputError("max_allowable_mw_ppg or leak_off_psi")
        return (frac - mw) * PSI_PER_PPG_FT * shoe

    @classmethod
    def kill_mw(cls, original_mw_ppg, sidpp_psi, tvd_ft) -> EngineeringResult:
        try:
            value = cls.calculate_kill_mw(original_mw_ppg, sidpp_psi, tvd_ft)
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
        return ok(
            value,
            values={"kill_mw_ppg": round(value, 4)},
            unit="ppg",
            formula="Kill MW = original MW + SIDPP / (0.052 × TVD)",
            method=cls.METHOD,
            assumptions=["SIDPP represents underbalance at bit TVD", "Oilfield constant 0.052 psi/ppg/ft"],
        )

    @classmethod
    def maasp(
        cls,
        max_allowable_mw_ppg=None,
        current_mw_ppg=None,
        shoe_tvd_ft=None,
        leak_off_psi=None,
    ) -> EngineeringResult:
        try:
            value = cls.calculate_maasp(
                max_allowable_mw_ppg, current_mw_ppg, shoe_tvd_ft, leak_off_psi
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
        return ok(
            value,
            values={"maasp_psi": round(value, 2)},
            unit="psi",
            formula="MAASP = (Frac MW − Current MW) × 0.052 × Shoe TVD",
            method=cls.METHOD,
            assumptions=["Weakest point is the casing shoe", "Frac MW from LOT or given equivalent MW"],
        )

    @classmethod
    def kick_tolerance(
        cls,
        mw_ppg,
        shoe_tvd_ft,
        current_tvd_ft,
        frac_mw_ppg=None,
        lot_pressure_psi=None,
        frac_gradient_psi_ft=None,
        influx_gradient_psi_ft=None,
        influx_emw_ppg=None,
        annular_capacity_bbl_ft=None,
        bha_annular_capacity_bbl_ft=None,
        bha_length_ft=None,
        formation_emw_ppg=None,
        formation_pressure_psi=None,
        annular_vol_bbl=None,
    ) -> EngineeringResult:
        """IWCF kick-tolerance (volume) with explicit inputs.

        ``annular_vol_bbl`` is retained as a compatibility parameter only.
        A total annular volume cannot be converted to the depth-dependent
        capacity required by this calculation without an additional geometry
        assumption, so supplying it is explicitly unsupported. Use
        ``annular_capacity_bbl_ft`` (and the optional BHA capacity/length)
        instead.

        Steps (IWCF / drillingformulas methodology):
        1. Kick intensity = formation EMW − current MW (if formation given)
        2. MAASP/MASICP = (LOT MW − MW) × 0.052 × shoe TVD
        3. Remaining shoe budget = MAASP − (kick intensity × 0.052 × TVD)
           If formation EMW is not given, remaining = MAASP (swabbed / balanced case)
        4. Influx height = remaining / (mud gradient − influx gradient)
        5. Volume at BHA = height × BHA/OH capacity (piecewise if height > BHA length)
        6. Volume at shoe = height × DP/OH capacity; Boyle to bottom:
           V_bottom = V_shoe × P_frac / P_formation
        7. Kick tolerance = the smaller of the two volumes

        Gas is the design influx (worst case). Influx gradient is REQUIRED —
        it is not defaulted to 0.1 psi/ft.
        """
        warnings: List[str] = []
        try:
            legacy_volume = optional_number(annular_vol_bbl, "annular_vol_bbl")
            if legacy_volume is not None:
                return unsupported(
                    "annular_vol_bbl is deprecated; supply annular_capacity_bbl_ft "
                    "because total volume cannot define a depth-dependent capacity"
                )
            mw = require_number(mw_ppg, "mw_ppg")
            shoe = require_number(shoe_tvd_ft, "shoe_tvd_ft")
            tvd = require_number(current_tvd_ft, "current_tvd_ft")
            if shoe <= 0:
                raise EngineeringError("shoe_tvd_ft must be > 0")
            if tvd <= 0:
                raise EngineeringError("current_tvd_ft must be > 0")
            if tvd < shoe:
                warnings.append("Current TVD is shallower than shoe TVD — check inputs")

            frac_mw = cls._frac_mw_ppg(shoe, frac_mw_ppg, lot_pressure_psi, frac_gradient_psi_ft)
            influx_g = cls._influx_gradient_psi_ft(influx_gradient_psi_ft, influx_emw_ppg)

            form_emw = optional_number(formation_emw_ppg, "formation_emw_ppg")
            form_psi = optional_number(formation_pressure_psi, "formation_pressure_psi")
            if form_emw is None and form_psi is not None:
                form_emw = form_psi / (PSI_PER_PPG_FT * tvd)
            if form_psi is None and form_emw is not None:
                form_psi = form_emw * PSI_PER_PPG_FT * tvd

            maasp = (frac_mw - mw) * PSI_PER_PPG_FT * shoe
            p_frac = frac_mw * PSI_PER_PPG_FT * shoe
            mud_g = mw * PSI_PER_PPG_FT

            if maasp < 0:
                return failed("Current MW exceeds fracture MW at the shoe (MAASP < 0)")

            kick_intensity = None
            underbalance = 0.0
            if form_emw is not None:
                kick_intensity = form_emw - mw
                underbalance = kick_intensity * PSI_PER_PPG_FT * tvd
                remaining = maasp - underbalance
            else:
                remaining = maasp
                warnings.append(
                    "Formation pressure / EMW not provided — using swabbed-kick "
                    "(SIDPP = 0) remaining budget = MAASP. Kick intensity is not computed."
                )

            max_sidpp = (frac_mw - mw) * PSI_PER_PPG_FT * tvd

            delta_g = mud_g - influx_g
            if delta_g <= 0:
                return unsupported(
                    "Influx gradient must be less than mud gradient to compute influx height"
                )

            if remaining <= 0:
                values = {
                    "maasp_psi": round(maasp, 2),
                    "kick_intensity_ppg": None if kick_intensity is None else round(kick_intensity, 4),
                    "underbalance_psi": round(underbalance, 2),
                    "remaining_pressure_psi": round(remaining, 2),
                    "max_kick_intensity_ppg": round(frac_mw - mw, 4),
                    "max_sidpp_psi": round(max_sidpp, 2),
                    "max_kick_height_ft": 0.0,
                    "kick_tolerance_bbl": 0.0,
                    "frac_mw_ppg": round(frac_mw, 4),
                    "influx_gradient_psi_ft": round(influx_g, 5),
                }
                return ok(
                    0.0,
                    values=values,
                    unit="bbl",
                    formula="KT = min(V_BHA, V_shoe×P_frac/P_form); height = remaining/(G_mud−G_influx)",
                    method=cls.METHOD,
                    assumptions=_kt_assumptions(),
                    warnings=warnings + ["Remaining shoe budget ≤ 0 — kick intensity exceeds MAASP"],
                    metadata={"units": _kt_units()},
                    scope="COMPLETE",
                )

            height = remaining / delta_g

            dp_cap = optional_number(annular_capacity_bbl_ft, "annular_capacity_bbl_ft")
            bha_cap = optional_number(bha_annular_capacity_bbl_ft, "bha_annular_capacity_bbl_ft")
            bha_len = optional_number(bha_length_ft, "bha_length_ft")

            vol_bha = None
            vol_shoe = None
            vol_bottom = None
            kt = None

            if dp_cap is None and bha_cap is None:
                warnings.append(
                    "Annular capacity not provided — height and pressures reported, "
                    "kick-tolerance volume not computed."
                )
            else:
                cap_open = dp_cap if dp_cap is not None else bha_cap
                if bha_cap is not None and bha_len is not None and bha_len > 0 and height > bha_len and cap_open is not None:
                    vol_bha = bha_len * bha_cap + (height - bha_len) * cap_open
                elif bha_cap is not None:
                    vol_bha = height * bha_cap
                elif cap_open is not None:
                    vol_bha = height * cap_open

                if cap_open is not None:
                    vol_shoe = height * cap_open
                    p_form = form_psi if form_psi is not None else mw * PSI_PER_PPG_FT * tvd
                    if p_form <= 0:
                        return failed("Formation pressure must be > 0 for Boyle conversion")
                    vol_bottom = vol_shoe * p_frac / p_form

                candidates = [v for v in (vol_bha, vol_bottom) if v is not None]
                if candidates:
                    kt = min(candidates)

            values = {
                "maasp_psi": round(maasp, 2),
                "kick_intensity_ppg": None if kick_intensity is None else round(kick_intensity, 4),
                "underbalance_psi": round(underbalance, 2),
                "remaining_pressure_psi": round(remaining, 2),
                "max_kick_intensity_ppg": round(frac_mw - mw, 4),
                "max_sidpp_psi": round(max_sidpp, 2),
                "max_kick_height_ft": round(height, 2),
                "volume_at_bha_bbl": None if vol_bha is None else round(vol_bha, 3),
                "volume_at_shoe_bbl": None if vol_shoe is None else round(vol_shoe, 3),
                "volume_at_bottom_bbl": None if vol_bottom is None else round(vol_bottom, 3),
                "kick_tolerance_bbl": None if kt is None else round(kt, 3),
                "frac_mw_ppg": round(frac_mw, 4),
                "influx_gradient_psi_ft": round(influx_g, 5),
                "mw_ppg": mw,
                "shoe_tvd_ft": shoe,
                "current_tvd_ft": tvd,
            }
            return ok(
                kt if kt is not None else height,
                values=values,
                unit="bbl" if kt is not None else "ft",
                formula=(
                    "MAASP=(FracMW−MW)×0.052×ShoeTVD; "
                    "height=remaining/(0.052×MW − G_influx); "
                    "KT=min(V_BHA, V_shoe×P_frac/P_form)"
                ),
                method=cls.METHOD,
                assumptions=_kt_assumptions(),
                warnings=warnings,
                metadata={"units": _kt_units()},
                scope="COMPLETE",
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def trip_margin(
        cls,
        mw_ppg,
        formation_emw_ppg=None,
        formation_pressure_psi=None,
        tvd_ft=None,
        swab_pressure_psi=None,
        required_trip_margin_ppg=None,
    ) -> EngineeringResult:
        """Trip margin = current MW − pore-pressure EMW.

        Optional swab pressure converts to an equivalent required trip margin:
        TM_required (ppg) = swab_psi / (0.052 × TVD)
        """
        try:
            mw = require_number(mw_ppg, "mw_ppg")
            tvd = optional_number(tvd_ft, "tvd_ft")
            form_emw = optional_number(formation_emw_ppg, "formation_emw_ppg")
            form_psi = optional_number(formation_pressure_psi, "formation_pressure_psi")
            if form_emw is None:
                if form_psi is None or tvd is None:
                    raise MissingInputError("formation_emw_ppg or (formation_pressure_psi and tvd_ft)")
                if tvd <= 0:
                    raise EngineeringError("tvd_ft must be > 0")
                form_emw = form_psi / (PSI_PER_PPG_FT * tvd)
            tm_ppg = mw - form_emw
            tm_psi = None
            if tvd is not None:
                if tvd <= 0:
                    raise EngineeringError("tvd_ft must be > 0")
                tm_psi = tm_ppg * PSI_PER_PPG_FT * tvd

            warnings: List[str] = []
            swab = optional_number(swab_pressure_psi, "swab_pressure_psi")
            req = optional_number(required_trip_margin_ppg, "required_trip_margin_ppg")
            if swab is not None:
                if tvd is None or tvd <= 0:
                    raise MissingInputError("tvd_ft (required to convert swab pressure)")
                req_from_swab = swab / (PSI_PER_PPG_FT * tvd)
                req = req_from_swab if req is None else max(req, req_from_swab)
            adequate = None
            if req is not None:
                adequate = tm_ppg >= req - 1e-9
                if not adequate:
                    warnings.append(
                        f"Trip margin {tm_ppg:.3f} ppg is below required {req:.3f} ppg"
                    )

            values = {
                "trip_margin_ppg": round(tm_ppg, 4),
                "trip_margin_psi": None if tm_psi is None else round(tm_psi, 2),
                "mw_ppg": mw,
                "formation_emw_ppg": round(form_emw, 4),
                "required_trip_margin_ppg": None if req is None else round(req, 4),
                "adequate": adequate,
            }
            return ok(
                tm_ppg,
                values=values,
                unit="ppg",
                formula="Trip margin (ppg) = MW − Pore EMW; psi = 0.052 × TM × TVD",
                method=cls.METHOD,
                assumptions=[
                    "Pore pressure expressed as equivalent mud weight at bit TVD",
                    "Swab, if given, is converted with 0.052 × TVD",
                    "Does not include cutting load or temperature effects",
                ],
                warnings=warnings,
                metadata={"units": {"mw": "ppg", "tvd": "ft", "pressure": "psi"}},
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def formation_pressure(
        cls,
        mw_ppg,
        tvd_ft,
        sidpp_psi=0.0,
    ) -> EngineeringResult:
        """Formation pressure from mud hydrostatics + shut-in drill-pipe pressure.

            P_hyd = 0.052 × MW × TVD
            P_form = P_hyd + SIDPP
            gradient = P_form / TVD
            EMW_form = P_form / (0.052 × TVD)

        SIDPP = 0 (balanced well) is allowed; negative SIDPP is rejected.
        TVD must be > 0 — no invented depth.
        """
        try:
            mw = require_number(mw_ppg, "mw_ppg")
            tvd = require_number(tvd_ft, "tvd_ft")
            sidpp = require_number(sidpp_psi, "sidpp_psi")
            if mw <= 0:
                raise EngineeringError("mw_ppg must be > 0")
            if tvd <= 0:
                raise EngineeringError("tvd_ft must be > 0")
            if sidpp < 0:
                raise EngineeringError("sidpp_psi cannot be negative")
            hyd = PSI_PER_PPG_FT * mw * tvd
            fp = hyd + sidpp
            gradient = fp / tvd
            emw = fp / (PSI_PER_PPG_FT * tvd)
            values = {
                "hydrostatic_psi": round(hyd, 2),
                "formation_pressure_psi": round(fp, 2),
                "pressure_gradient_psi_ft": round(gradient, 4),
                "equivalent_mw_ppg": round(emw, 4),
                "mw_ppg": mw,
                "tvd_ft": tvd,
                "sidpp_psi": sidpp,
            }
            return ok(
                round(fp, 2),
                values=values,
                unit="psi",
                formula="P_form = 0.052×MW×TVD + SIDPP; EMW = P_form/(0.052×TVD)",
                method=cls.METHOD,
                assumptions=[
                    "SIDPP is measured with the well shut in and the bit on bottom",
                    "Gradient and EMW are averages over the full TVD",
                ],
                metadata={"units": {"pressure": "psi", "mw": "ppg", "tvd": "ft"}},
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def kick_volume(
        cls,
        pit_gain_bbl=None,
        annular_capacity_bbl_ft=None,
        bha_annular_capacity_bbl_ft=None,
        bha_length_ft=None,
        mw_ppg=None,
        sidpp_psi=None,
        sicp_psi=None,
        tvd_ft=None,
        influx_emw_ppg=None,
        influx_gradient_psi_ft=None,
    ) -> EngineeringResult:
        """Kick volume / height from pit gain and annular geometry.

        A positive number is not assumed to be a kick — pit gain must be provided
        and > 0, and annular capacity is required to convert volume to height.
        Optional SIDPP/SICP estimate the influx gradient.
        """
        try:
            gain = optional_number(pit_gain_bbl, "pit_gain_bbl")
            if gain is None:
                raise MissingInputError("pit_gain_bbl")
            if gain < 0:
                raise EngineeringError("pit_gain_bbl cannot be negative")
            if gain == 0:
                return ok(
                    0.0,
                    values={"kick_volume_bbl": 0.0, "kick_height_ft": 0.0, "is_kick": False},
                    unit="bbl",
                    formula="Height = pit gain / annular capacity",
                    method=cls.METHOD,
                    warnings=["Pit gain is 0 — no kick volume"],
                )

            dp_cap = optional_number(annular_capacity_bbl_ft, "annular_capacity_bbl_ft")
            bha_cap = optional_number(bha_annular_capacity_bbl_ft, "bha_annular_capacity_bbl_ft")
            bha_len = optional_number(bha_length_ft, "bha_length_ft")
            if dp_cap is None and bha_cap is None:
                raise MissingInputError("annular_capacity_bbl_ft")
            if dp_cap is not None and dp_cap <= 0:
                raise EngineeringError("annular_capacity_bbl_ft must be > 0")
            if bha_cap is not None and bha_cap <= 0:
                raise EngineeringError("bha_annular_capacity_bbl_ft must be > 0")

            # Piecewise height: fill BHA annulus first, then DP/OH.
            if bha_cap and bha_len and bha_len > 0:
                bha_vol = bha_cap * bha_len
                if gain <= bha_vol:
                    height = gain / bha_cap
                    location = "bha_annulus"
                else:
                    if dp_cap is None:
                        raise MissingInputError("annular_capacity_bbl_ft (kick taller than BHA)")
                    height = bha_len + (gain - bha_vol) / dp_cap
                    location = "open_hole_and_bha"
            else:
                cap = bha_cap if dp_cap is None else dp_cap
                height = gain / cap
                location = "uniform_annulus"

            warnings: List[str] = []
            influx_g = None
            mw = optional_number(mw_ppg, "mw_ppg")
            sidpp = optional_number(sidpp_psi, "sidpp_psi")
            sicp = optional_number(sicp_psi, "sicp_psi")
            tvd = optional_number(tvd_ft, "tvd_ft")
            if sidpp is not None and sicp is not None and mw is not None and height > 0:
                # SICP − SIDPP ≈ (G_mud − G_influx) × height
                influx_g = mw * PSI_PER_PPG_FT - (sicp - sidpp) / height
                if influx_g < 0:
                    warnings.append("Computed influx gradient < 0 — check SICP/SIDPP/height")
            elif influx_gradient_psi_ft not in (None, ""):
                influx_g = require_number(influx_gradient_psi_ft, "influx_gradient_psi_ft")
            elif influx_emw_ppg not in (None, ""):
                influx_g = require_number(influx_emw_ppg, "influx_emw_ppg") * PSI_PER_PPG_FT

            kick_type = None
            if influx_g is not None:
                if influx_g < 0.12:
                    kick_type = "gas"
                elif influx_g < 0.35:
                    kick_type = "oil_or_condensate"
                else:
                    kick_type = "salt_water"

            values = {
                "kick_volume_bbl": round(gain, 3),
                "kick_height_ft": round(height, 2),
                "is_kick": gain > 0,
                "location": location,
                "influx_gradient_psi_ft": None if influx_g is None else round(influx_g, 5),
                "kick_type": kick_type,
                "sidpp_psi": sidpp,
                "sicp_psi": sicp,
                "tvd_ft": tvd,
            }
            return ok(
                gain,
                values=values,
                unit="bbl",
                formula="V = pit gain; H = V / annular capacity (BHA then DP/OH); G_i from SICP−SIDPP",
                method=cls.METHOD,
                assumptions=[
                    "Pit gain is entirely formation influx (no surface additions)",
                    "Annulus is fully occupied by influx over the computed height",
                    "SICP−SIDPP method assumes influx still around the BHA/OH",
                ],
                warnings=warnings,
                metadata={"units": {"volume": "bbl", "height": "ft", "gradient": "psi/ft"}},
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))


# ------------------------------------------------------------------
    # Fracture gradient — Eaton (1969) correlation
    # ------------------------------------------------------------------
    @classmethod
    def eaton_fracture_gradient(
        cls,
        overburden_gradient_psi_ft,
        pore_pressure_gradient_psi_ft,
        poisson_ratio=0.25,
    ) -> EngineeringResult:
        """Eaton (1969) fracture gradient correlation.

            FG = (ν / (1 − ν)) × (OBG − PPG) + PPG

        ν = Poisson's ratio of the formation (0.2–0.5, default 0.25).
        All gradients in psi/ft. FG is the fracture gradient at the
        depth where OBG/PPG apply; multiply by TVD to get fracture
        pressure (see maasp/kick_tolerance for the pressure use).
        """
        try:
            obg = require_number(overburden_gradient_psi_ft, "overburden_gradient_psi_ft")
            ppg = require_number(pore_pressure_gradient_psi_ft, "pore_pressure_gradient_psi_ft")
            nu = require_number(poisson_ratio, "poisson_ratio")
            if not (0.0 < nu < 0.5):
                raise EngineeringError("Poisson's ratio must be in (0, 0.5)")
            if obg <= 0 or ppg <= 0:
                raise EngineeringError("Gradients must be > 0")
            if ppg > obg:
                raise EngineeringError(
                    "Pore pressure gradient cannot exceed overburden gradient"
                )
            ratio = nu / (1.0 - nu)
            fg = ratio * (obg - ppg) + ppg
            return ok(
                round(fg, 5),
                values={
                    "fracture_gradient_psi_ft": round(fg, 5),
                    "poisson_ratio": nu,
                    "overburden_gradient_psi_ft": obg,
                    "pore_pressure_gradient_psi_ft": ppg,
                },
                unit="psi/ft",
                formula="FG = (ν/(1−ν)) × (OBG − PPG) + PPG",
                method="Eaton (1969), JPT",
                assumptions=[
                    "Gradients in psi/ft at the depth of interest",
                    "Poisson's ratio 0.25 unless provided (sandstone ≈ 0.25)",
                    "Multiply FG × TVD(ft) for fracture pressure (psi)",
                ],
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    # ------------------------------------------------------------------
    # Kick fluid type from shut-in pressures and pit gain
    # ------------------------------------------------------------------
    @classmethod
    def influx_type(
        cls,
        sicp_psi,
        sidpp_psi,
        annular_capacity_bbl_ft,
        pit_gain_bbl,
    ) -> EngineeringResult:
        """Estimate influx fluid type (gas / oil / saltwater).

        Influx height = pit gain / annular capacity
        Influx gradient = (SICP − SIDPP) / height

        Classification (common field cut-offs, psi/ft):
            < 0.12  → gas
            0.12–0.35 → oil
            > 0.35  → saltwater

        Gas is the worst case for kick tolerance (lowest gradient).
        """
        try:
            sicp = require_number(sicp_psi, "sicp_psi")
            sidpp = require_number(sidpp_psi, "sidpp_psi")
            cap = require_number(annular_capacity_bbl_ft, "annular_capacity_bbl_ft")
            gain = require_number(pit_gain_bbl, "pit_gain_bbl")
            if cap <= 0:
                raise EngineeringError("annular_capacity_bbl_ft must be > 0")
            if gain <= 0:
                raise EngineeringError("pit_gain_bbl must be > 0")
            if sicp < sidpp:
                raise EngineeringError(
                    "SICP cannot be less than SIDPP (check shut-in pressures)"
                )
            height = gain / cap
            gradient = (sicp - sidpp) / height
            if gradient < 0.12:
                kind = "gas"
            elif gradient < 0.35:
                kind = "oil"
            else:
                kind = "saltwater"
            return ok(
                kind,
                values={
                    "influx_type": kind,
                    "influx_gradient_psi_ft": round(gradient, 4),
                    "influx_height_ft": round(height, 2),
                    "sicp_psi": sicp,
                    "sidpp_psi": sidpp,
                    "pit_gain_bbl": gain,
                },
                unit="category",
                formula="∇influx = (SICP − SIDPP) / (pit gain / annular capacity)",
                method="Field classification (gas < 0.12, oil < 0.35, else water)",
                assumptions=[
                    "Single influx, uniform annular capacity over the influx height",
                    "Cut-offs in psi/ft: gas < 0.12, oil < 0.35, saltwater ≥ 0.35",
                    "Gas is the worst case for kick tolerance calculations",
                ],
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))


def _kt_assumptions() -> List[str]:
    return [
        "IWCF methodology: gas influx, weakest point at the casing shoe",
        "Boyle conversion of shoe volume to bottom-hole condition using P_frac / P_form",
        "Oilfield constant 0.052 psi/ppg/ft",
        "No temperature / z-factor / migration correction (single-bubble screening)",
        "Influx gradient is a required input — not defaulted",
    ]


def _kt_units() -> Dict[str, str]:
    return {
        "mw": "ppg",
        "tvd": "ft",
        "pressure": "psi",
        "capacity": "bbl/ft",
        "volume": "bbl",
        "height": "ft",
        "influx_gradient": "psi/ft",
    }
