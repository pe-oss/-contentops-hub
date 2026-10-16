"""
Kịch bản kiểm chứng độc lập tính năng Concurrency / Row Locking / OCC trên PostgreSQL thực tế.
"""
import os
import sys
import time
import threading
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.db import connection, connections
from django.contrib.auth import get_user_model
from apps.workspaces.models import Workspace, BrandProfile
from apps.workspaces.services import (
    save_brand_profile,
    ConcurrencyConflictError,
    create_workspace_with_owner,
)

User = get_user_model()


def test_pessimistic_row_locking():
    print("\n--- [1] KIỂM TRA PESSIMISTIC ROW LOCKING (select_for_update) ---")
    test_user, _ = User.objects.get_or_create(username="concurrency_tester", email="conc@example.com")
    workspace = Workspace.objects.filter(name="Concurrency WS").first()
    if not workspace:
        workspace = create_workspace_with_owner(user=test_user, name="Concurrency WS")
    bp, _ = BrandProfile.objects.get_or_create(
        workspace=workspace,
        defaults={
            "name": "Initial Name",
            "product_summary": "Initial Product Summary",
            "target_audience": "Audience 101",
            "revision": 1,
        },
    )

    events = []
    barrier = threading.Barrier(2)

    def tx1():
        conn = connections.create_connection("default")
        try:
            with conn.cursor() as cursor:
                cursor.execute("BEGIN;")
                events.append(("tx1_begin", time.time()))
                cursor.execute("SELECT id, name FROM workspaces_brandprofile WHERE id = %s FOR UPDATE;", [str(bp.id)])
                events.append(("tx1_locked", time.time()))
                barrier.wait(timeout=5)
                time.sleep(1.5)
                cursor.execute("UPDATE workspaces_brandprofile SET name = 'Updated by TX1' WHERE id = %s;", [str(bp.id)])
                cursor.execute("COMMIT;")
                events.append(("tx1_commit", time.time()))
        finally:
            conn.close()

    def tx2():
        conn = connections.create_connection("default")
        try:
            barrier.wait(timeout=5)
            time.sleep(0.1)
            with conn.cursor() as cursor:
                cursor.execute("BEGIN;")
                t_start = time.time()
                events.append(("tx2_attempt_lock", t_start))
                cursor.execute("SELECT id, name FROM workspaces_brandprofile WHERE id = %s FOR UPDATE;", [str(bp.id)])
                t_acquired = time.time()
                events.append(("tx2_acquired_lock", t_acquired))
                duration = t_acquired - t_start
                print(f"    * TX2 bị block trong: {duration:.3f} giây (kỳ vọng >= 1.0s do chờ TX1 commit)")
                assert duration >= 1.0, f"TX2 không bị khóa đúng cách! Chỉ mất {duration}s"
                cursor.execute("COMMIT;")
                events.append(("tx2_commit", time.time()))
        finally:
            conn.close()

    t1 = threading.Thread(target=tx1)
    t2 = threading.Thread(target=tx2)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    event_dict = {name: t for name, t in events}
    print(f"    * TX1 Locked at:        {event_dict['tx1_locked']:.3f}")
    print(f"    * TX2 Attempted at:     {event_dict['tx2_attempt_lock']:.3f}")
    print(f"    * TX1 Committed at:     {event_dict['tx1_commit']:.3f}")
    print(f"    * TX2 Lock Acquired at: {event_dict['tx2_acquired_lock']:.3f}")
    assert event_dict['tx2_acquired_lock'] >= event_dict['tx1_commit'], "TX2 phải có lock sau khi TX1 commit!"
    print("    => [PASS] PostgreSQL Row Locking (SELECT FOR UPDATE) hoạt động chính xác tuyệt đối!")


def test_optimistic_concurrency_control():
    print("\n--- [2] KIỂM TRA OPTIMISTIC CONCURRENCY CONTROL (OCC) ---")
    test_user = User.objects.get(username="concurrency_tester")
    workspace = Workspace.objects.get(name="Concurrency WS")
    bp = BrandProfile.objects.get(workspace=workspace)
    current_rev = bp.revision

    results = []
    barrier = threading.Barrier(2)

    def worker(worker_id):
        connection.close()
        try:
            barrier.wait(timeout=5)
            res = save_brand_profile(
                workspace=workspace,
                user=test_user,
                name=f"Brand by Worker {worker_id}",
                product_summary="Test Product Summary",
                target_audience="Test Audience",
                expected_revision=current_rev,
            )
            results.append((worker_id, "SUCCESS", res.revision))
        except ConcurrencyConflictError as cce:
            results.append((worker_id, "OCC_CONFLICT_409", str(cce)))
        except Exception as e:
            results.append((worker_id, "ERROR", str(e)))
        finally:
            connection.close()

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    print(f"    * Kết quả xử lý 2 threads đồng thời:")
    for wid, status, detail in results:
        print(f"      - Worker {wid}: {status} ({detail})")

    successes = [r for r in results if r[1] == "SUCCESS"]
    conflicts = [r for r in results if r[1] == "OCC_CONFLICT_409"]
    assert len(successes) == 1, f"Chỉ đúng 1 worker thành công, thực tế: {len(successes)}"
    assert len(conflicts) == 1, f"Đúng 1 worker phải xung đột 409 OCC, thực tế: {len(conflicts)}"
    print("    => [PASS] Optimistic Concurrency Control (OCC) loại trừ race condition chính xác!")


if __name__ == "__main__":
    test_pessimistic_row_locking()
    test_optimistic_concurrency_control()
    print("\n=== TOÀN BỘ KIỂM CHỨNG CONCURRENCY TRÊN POSTGRESQL THÀNH CÔNG RỰC RỠ! ===\n")
