import textwrap

import pytest

from app.models.route import Route
from app.domains.sports.track_service import parse_gpx_points, process_track

GPX = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="test">
      <trk><name>t</name><trkseg>
        <trkpt lat="30.1200" lon="118.8200"><ele>420</ele></trkpt>
        <trkpt lat="30.1250" lon="118.8250"><ele>520</ele></trkpt>
        <trkpt lat="30.1300" lon="118.8300"><ele>620</ele></trkpt>
        <trkpt lat="30.1350" lon="118.8350"><ele>720</ele></trkpt>
        <trkpt lat="30.1420" lon="118.8420"><ele>800</ele></trkpt>
      </trkseg></trk>
    </gpx>
    """)


def test_parse_gpx_points():
    pts = parse_gpx_points(GPX)
    assert len(pts) == 5
    assert pts[0][0] == 30.12 and pts[0][2] == 420.0


async def test_process_track_updates_route(db):
    route = Route(name="t", region="r", sport="hiking", difficulty=1,
                  distance_km=0.0, climb_m=0, clarity="low")
    db.add(route)
    await db.commit()
    summary = await process_track(db, route, GPX)
    assert summary.distance_km > 0
    assert summary.climb_m >= 90
    assert route.distance_km > 0 and route.climb_m >= 90
    assert route.elevation and route.elevation[0]["m"] == 420
    assert len(route.track_points) <= 500


async def test_process_track_insufficient_points(db):
    route = Route(name="x", region="r", sport="hiking", difficulty=1, distance_km=0.0, climb_m=0, clarity="low")
    db.add(route)
    await db.commit()
    with pytest.raises(ValueError):
        await process_track(db, route, '<?xml version="1.0"?><gpx version="1.1"><trk><trkseg><trkpt lat="30.12" lon="118.82"/></trkseg></trk></gpx>')


NOELE_GPX = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="test">
      <trk><name>t</name><trkseg>
        <trkpt lat="30.1200" lon="118.8200"></trkpt>
        <trkpt lat="30.1250" lon="118.8250"></trkpt>
        <trkpt lat="30.1300" lon="118.8300"></trkpt>
      </trkseg></trk>
    </gpx>
    """)


async def test_process_track_no_elevation(db):
    route = Route(name="noele", region="r", sport="hiking", difficulty=1,
                  distance_km=0.0, climb_m=0, clarity="low")
    db.add(route)
    await db.commit()
    summary = await process_track(db, route, NOELE_GPX)
    assert summary.distance_km > 0
    assert summary.climb_m == 0
    assert route.elevation == []
