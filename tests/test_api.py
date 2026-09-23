import pytest

P = "/api/v1"
A = {"Authorization": "Bearer parent-a"}
B = {"Authorization": "Bearer parent-b"}
ADMIN = {"Authorization": "Bearer admin"}
REVIEWER = {"Authorization": "Bearer reviewer"}
REVIEWER_B = {"Authorization": "Bearer reviewer-b"}


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
        for gate in ("curriculum", "safety", "assets"):
            r = await client.post(
                P + f"/admin/courses/{c['id']}/reviews",
                headers=REVIEWER,
                json={"review_gate": gate, "decision": "approved", "notes": "Reviewed"},
            )
            assert r.status_code == 201, r.text
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
    evidence = (
        await client.put(route, headers=A, json={"status": "completed", "progress_percent": 100})
    ).json()
    assert evidence["completion_source"] == "parent_self_reported"
    assert evidence["mastery_verified"] is False
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
    missing = await client.post(P + f"/admin/courses/{c['id']}/publish", headers=ADMIN)
    assert missing.status_code == 409
    for gate in ("curriculum", "safety", "assets"):
        assert (
            await client.post(
                P + f"/admin/courses/{c['id']}/reviews",
                headers=REVIEWER,
                json={"review_gate": gate, "decision": "approved"},
            )
        ).status_code == 201
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


@pytest.mark.asyncio
async def test_publication_reviews_are_independent_immutable_and_content_bound(client):
    course, module, lessons = await create_course(client, publish=False)
    review_url = P + f"/admin/courses/{course['id']}/reviews"
    self_review = await client.post(
        review_url,
        headers=ADMIN,
        json={"review_gate": "curriculum", "decision": "approved"},
    )
    assert self_review.status_code == 403

    status = (await client.get(review_url, headers=ADMIN)).json()
    assert status["ready_to_publish"] is False
    assert status["missing_gates"] == ["curriculum", "safety", "assets"]

    for gate in ("curriculum", "safety", "assets"):
        reviewed = await client.post(
            review_url,
            headers=REVIEWER,
            json={"review_gate": gate, "decision": "approved", "notes": "Checked"},
        )
        assert reviewed.status_code == 201
        duplicate = await client.post(
            review_url,
            headers=REVIEWER,
            json={"review_gate": gate, "decision": "approved"},
        )
        assert duplicate.status_code == 409

    assert (await client.get(review_url, headers=ADMIN)).json()["ready_to_publish"] is True
    assert (
        await client.post(P + f"/admin/courses/{course['id']}/publish", headers=ADMIN)
    ).status_code == 200

    await client.patch(
        P + f"/admin/courses/{course['id']}", headers=ADMIN, json={"status": "draft"}
    )
    await client.patch(
        P + f"/admin/lessons/{lessons[0]['id']}",
        headers=ADMIN,
        json={"title": "Changed after review"},
    )
    stale = (await client.get(review_url, headers=ADMIN)).json()
    assert stale["ready_to_publish"] is False
    assert stale["missing_gates"] == ["curriculum", "safety", "assets"]
    assert (
        await client.post(P + f"/admin/courses/{course['id']}/publish", headers=ADMIN)
    ).status_code == 409


@pytest.mark.asyncio
async def test_rejected_review_blocks_publication_even_with_another_approval(client):
    course, _, _ = await create_course(client, publish=False)
    review_url = P + f"/admin/courses/{course['id']}/reviews"
    rejected = await client.post(
        review_url,
        headers=REVIEWER,
        json={"review_gate": "safety", "decision": "rejected", "notes": "Needs changes"},
    )
    assert rejected.status_code == 201
    for gate in ("curriculum", "safety", "assets"):
        approved = await client.post(
            review_url,
            headers=REVIEWER_B,
            json={"review_gate": gate, "decision": "approved"},
        )
        assert approved.status_code == 201
    status = (await client.get(review_url, headers=ADMIN)).json()
    assert status["rejected_gates"] == ["safety"]
    assert status["ready_to_publish"] is False
    blocked = await client.post(P + f"/admin/courses/{course['id']}/publish", headers=ADMIN)
    assert blocked.status_code == 409
