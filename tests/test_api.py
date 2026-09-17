import pytest

P = "/api/v1"
A = {"Authorization": "Bearer parent-a"}
B = {"Authorization": "Bearer parent-b"}
ADMIN = {"Authorization": "Bearer admin"}


async def create_course(client, slug="coding", publish=True):
    r = await client.post(
        P + "/admin/courses",
        headers=ADMIN,
        json={
            "slug": slug,
            "title": "Coding",
            "short_description": "Learn clear instructions",
            "age_band": "8-10",
            "category": "Coding",
        },
    )
    assert r.status_code == 201, r.text
    c = r.json()
    r = await client.post(
        P + f"/admin/courses/{c['id']}/modules",
        headers=ADMIN,
        json={"title": "First steps", "position": 0},
    )
    assert r.status_code == 201, r.text
    m = r.json()
    lessons = []
    for i in range(2):
        r = await client.post(
            P + f"/admin/modules/{m['id']}/lessons",
            headers=ADMIN,
            json={
                "title": f"Lesson {i}",
                "slug": f"lesson-{i}",
                "position": i,
                "content": {
                    "blocks": [
                        {"type": "paragraph", "text": "A program is a list of instructions."},
                        {"type": "activity", "text": "Write steps to draw a square."},
                    ]
                },
            },
        )
        assert r.status_code == 201, r.text
        lessons.append(r.json())
    if publish:
        r = await client.post(P + f"/admin/courses/{c['id']}/publish", headers=ADMIN)
        assert r.status_code == 200, r.text
    return c, m, lessons


async def child(client, headers=A):
    r = await client.post(
        P + "/students", headers=headers, json={"first_name": "Sample", "age_band": "8-10"}
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_full_journey_and_permissions(client):
    assert (await client.get(P + "/health")).status_code == 200
    assert (await client.get(P + "/students")).status_code == 401
    assert (
        await client.get(P + "/me", headers={"Authorization": "Bearer disabled"})
    ).status_code == 403
    assert (await client.get(P + "/me", headers=A)).json()["role"] == "parent"
    c, m, lessons = await create_course(client)
    s = await child(client)
    assert (await client.get(P + f"/students/{s['id']}", headers=B)).status_code == 404
    assert (
        await client.patch(P + f"/students/{s['id']}", headers=B, json={"first_name": "Stolen"})
    ).status_code == 404
    assert (await client.get(P + "/admin/courses", headers=A)).status_code == 403
    catalog = (await client.get(P + "/courses")).json()
    assert len(catalog) == 1
    assert "content" not in catalog[0]["lessons"][0]
    assert (await client.get(P + f"/lessons/{lessons[0]['id']}", headers=A)).status_code == 403
    r = await client.post(
        P + f"/students/{s['id']}/enrollments", headers=A, json={"course_id": c["id"]}
    )
    assert r.status_code == 200, r.text
    e = r.json()
    duplicate = await client.post(
        P + f"/students/{s['id']}/enrollments", headers=A, json={"course_id": c["id"]}
    )
    assert duplicate.json()["id"] == e["id"]
    assert (await client.get(P + f"/enrollments/{e['id']}", headers=B)).status_code == 404
    assert (await client.get(P + f"/enrollments/{e['id']}/progress", headers=B)).status_code == 404
    assert (await client.get(P + f"/courses/{c['id']}/modules", headers=A)).json()[0]["lessons"][0][
        "content"
    ]
    route = P + f"/enrollments/{e['id']}/lessons/{lessons[0]['id']}/progress"
    assert (
        await client.put(route, headers=B, json={"status": "completed", "progress_percent": 100})
    ).status_code == 404
    assert (
        await client.put(route, headers=A, json={"status": "completed", "progress_percent": 90})
    ).status_code == 422
    assert (
        await client.put(route, headers=A, json={"status": "completed", "progress_percent": 100})
    ).status_code == 200
    assert (
        await client.put(route, headers=A, json={"status": "completed", "progress_percent": 100})
    ).status_code == 200
    assert (await client.get(P + f"/enrollments/{e['id']}/progress", headers=A)).json()[
        "progress_percent"
    ] == 50
    assert (
        await client.put(route, headers=A, json={"status": "not_started", "progress_percent": 0})
    ).status_code == 409
    route2 = P + f"/enrollments/{e['id']}/lessons/{lessons[1]['id']}/progress"
    assert (
        await client.put(route2, headers=A, json={"status": "completed", "progress_percent": 100})
    ).status_code == 200
    assert (await client.get(P + f"/enrollments/{e['id']}", headers=A)).json()[
        "status"
    ] == "completed"
    assert (await client.get(P + f"/enrollments/{e['id']}/progress", headers=A)).json()[
        "progress_percent"
    ] == 100


@pytest.mark.asyncio
async def test_draft_and_cross_course_boundaries(client):
    c, m, lessons = await create_course(client, publish=False)
    assert (await client.get(P + "/courses")).json() == []
    assert (await client.get(P + "/courses/coding")).status_code == 404
    s = await child(client)
    assert (
        await client.post(
            P + f"/students/{s['id']}/enrollments", headers=A, json={"course_id": c["id"]}
        )
    ).status_code == 404
    await client.post(P + f"/admin/courses/{c['id']}/publish", headers=ADMIN)
    other, _, other_lessons = await create_course(client, slug="other")
    e = (
        await client.post(
            P + f"/students/{s['id']}/enrollments", headers=A, json={"course_id": c["id"]}
        )
    ).json()
    assert (
        await client.put(
            P + f"/enrollments/{e['id']}/lessons/{other_lessons[0]['id']}/progress",
            headers=A,
            json={"status": "completed", "progress_percent": 100},
        )
    ).status_code == 404
    assert (
        await client.post(
            P + f"/admin/courses/{c['id']}/modules",
            headers=ADMIN,
            json={"title": "late", "position": 2},
        )
    ).status_code == 409
    await client.patch(P + f"/admin/courses/{c['id']}", headers=ADMIN, json={"status": "draft"})
    assert (await client.get(P + f"/lessons/{lessons[0]['id']}", headers=A)).status_code == 404


@pytest.mark.asyncio
async def test_validation_conflicts_and_paid_course(client):
    assert (
        await client.post(P + "/students", headers=A, json={"first_name": "  ", "age_band": "8-10"})
    ).status_code == 422
    assert (
        await client.post(
            P + "/students",
            headers=A,
            json={"first_name": "Kid", "age_band": "8-10", "role": "admin"},
        )
    ).status_code == 422
    s = await child(client)
    assert (
        await client.patch(P + f"/students/{s['id']}", headers=A, json={"first_name": None})
    ).status_code == 422
    c, m, lessons = await create_course(client)
    duplicate = await client.post(
        P + "/admin/courses",
        headers=ADMIN,
        json={
            "slug": "coding",
            "title": "Duplicate",
            "short_description": "x",
            "age_band": "8-10",
            "category": "Coding",
        },
    )
    assert duplicate.status_code == 409
    assert (await client.get(P + "/courses")).status_code == 200
    await client.patch(P + f"/admin/courses/{c['id']}", headers=ADMIN, json={"is_free": False})
    assert (
        await client.post(
            P + f"/students/{s['id']}/enrollments", headers=A, json={"course_id": c["id"]}
        )
    ).status_code == 409
    assert (await client.get(P + "/students/not-a-uuid", headers=A)).status_code == 422


@pytest.mark.asyncio
async def test_empty_course_cannot_publish_and_learner_limit(client):
    r = await client.post(
        P + "/admin/courses",
        headers=ADMIN,
        json={
            "slug": "empty",
            "title": "Empty",
            "short_description": "x",
            "age_band": "8-10",
            "category": "Coding",
        },
    )
    assert (
        await client.post(P + f"/admin/courses/{r.json()['id']}/publish", headers=ADMIN)
    ).status_code == 409
    for _ in range(10):
        await child(client)
    assert (
        await client.post(
            P + "/students", headers=A, json={"first_name": "Overflow", "age_band": "8-10"}
        )
    ).status_code == 409
