"""Optional welleng integration; the built-in trajectory engine remains the fallback."""
class WellengAdapter:
    package = "welleng"

    @staticmethod
    def available():
        try:
            import welleng  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def build_survey(points, name="NNNN survey"):
        if not WellengAdapter.available():
            return None
        import welleng as we
        md = [float(p.get("md", 0)) for p in points]
        inc = [float(p.get("inc", p.get("inclination", 0)) or 0) for p in points]
        azi = [float(p.get("azi", p.get("azimuth", 0)) or 0) for p in points]
        if not md:
            return None
        header = we.survey.SurveyHeader(name=name, azi_reference="grid")
        return we.survey.Survey(md=md, inc=inc, azi=azi, header=header)
