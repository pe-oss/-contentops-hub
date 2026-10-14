import datetime
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.workspaces.models import (
    AccessRole, ContentApproval, ContentItem, ContentItemState,
    ContentPublication, ContentVersion, EmploymentType, Membership,
    MembershipStatus, Package, PackageStatus, Task, TaskRole, TaskStatus, Workspace,
)
from apps.workspaces.services import (
    ConcurrencyConflictError,
    add_content_item,
    approve_plan,
    block_content_item,
    cancel_content_item,
    create_editor_version,
    create_package,
    create_workspace_with_owner,
    owner_approve_item,
    record_content_publication,
    reopen_content_item,
    start_writing_task,
    submit_content_version,
    submit_for_owner_review,
    unblock_content_item,
    update_publication_metadata,
)

User = get_user_model()


class ContentPublicationB07Tests(TestCase):
    """
    Bộ kiểm thử B07 — Ghi nhận xuất bản nội dung và hoàn thành gói (Spec F06, 6.1, 6.2, 9, 13 B07, AC12, AC13, AC14).
    """

    def setUp(self):
        # 1. Khởi tạo Chủ workspace
        self.owner = User.objects.create_user(
            username="owner_pub",
            email="owner_pub@test.com",
            password="password123",
        )
        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="Doanh nghiệp Xuất bản B07",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.owner_membership = Membership.objects.get(workspace=self.workspace, user=self.owner)

        # 2. Thành viên Writer, Editor, Publisher
        self.writer = User.objects.create_user(username="writer_pub", email="writer_pub@test.com", password="password123")
        self.writer_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.writer,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        self.editor = User.objects.create_user(username="editor_pub", email="editor_pub@test.com", password="password123")
        self.editor_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.editor,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        self.publisher = User.objects.create_user(username="publisher_pub", email="publisher_pub@test.com", password="password123")
        self.publisher_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.publisher,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
        )

        # 3. Tạo Gói nội dung và bài viết mẫu
        now = timezone.now().date()
        self.package = create_package(
            user=self.owner,
            workspace=self.workspace,
            name="Gói Chiến dịch Mùa hè B07",
            objective="Tăng trưởng nhận diện thương hiệu qua kênh Facebook",
            coordinator_membership=self.owner_membership,
            start_date=now,
            end_date=now + datetime.timedelta(days=30),
            channel="FACEBOOK",
        )

        t_now = timezone.now()
        self.item = add_content_item(
            user=self.owner,
            package=self.package,
            title="Bài viết #1: Giới thiệu sản phẩm mới",
            brief="Mô tả các tính năng nổi bật và lợi ích người dùng.",
            cta="Đăng ký ngay hôm nay",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
            writing_deadline=t_now + datetime.timedelta(days=2),
            editing_deadline=t_now + datetime.timedelta(days=4),
            review_deadline=t_now + datetime.timedelta(days=5),
            planned_publish_at=t_now + datetime.timedelta(days=7),
        )

        approve_plan(user=self.owner, package=self.package)
        self.package.refresh_from_db()
        self.item.refresh_from_db()

        # Đưa bài viết tới READY_TO_PUBLISH qua luồng hợp lệ
        start_writing_task(user=self.writer, item=self.item)
        submit_content_version(user=self.writer, item=self.item, text="Nội dung bài viết v1 chuẩn SEO.")
        self.item.refresh_from_db()
        CHECKLIST_OK = {"brief_compliance": True, "factual_accuracy": True, "voice_tone": True, "cta_verified": True}
        submit_for_owner_review(user=self.editor, item=self.item, checklist=CHECKLIST_OK)
        self.item.refresh_from_db()
        self.approval, self.item = owner_approve_item(
            user=self.owner,
            item=self.item,
            expected_version_id=self.item.latest_version_id,
            expected_row_version=self.item.row_version,
        )

        # HTTP Clients
        self.client_publisher = Client()
        self.client_publisher.force_login(self.publisher)

        self.client_owner = Client()
        self.client_owner.force_login(self.owner)

        self.client_writer = Client()
        self.client_writer.force_login(self.writer)

        self.client_editor = Client()
        self.client_editor.force_login(self.editor)

    def test_record_publication_success_publisher(self):
        """
        Ghi nhận xuất bản thành công bởi Người xuất bản được phân công (Spec F06, AC13):
        - Tạo bản ghi ContentPublication đầy đủ thông tin.
        - Trạng thái bài viết chuyển READY_TO_PUBLISH -> PUBLISHED, row_version tăng.
        - Task PUBLISH chuyển trạng thái sang DONE.
        """
        pub_url = "https://facebook.com/permalink.php?story_fbid=123456"
        pub_time = timezone.now() - datetime.timedelta(minutes=15)
        row_v_before = self.item.row_version

        pub, updated_item = record_content_publication(
            user=self.publisher,
            item=self.item,
            url=pub_url,
            published_at=pub_time,
            expected_row_version=row_v_before,
            idempotency_key="pub_key_001",
        )

        self.assertIsNotNone(pub.id)
        self.assertEqual(pub.workspace, self.workspace)
        self.assertEqual(pub.item, updated_item)
        self.assertEqual(pub.version, updated_item.latest_version)
        self.assertEqual(pub.approval, self.approval)
        self.assertEqual(pub.url, pub_url)
        self.assertEqual(pub.published_at, pub_time)
        self.assertEqual(pub.recorded_by, self.publisher)

        # Kiểm tra trạng thái bài viết và row_version
        self.assertEqual(updated_item.state, ContentItemState.PUBLISHED)
        self.assertEqual(updated_item.row_version, row_v_before + 1)

        # Kiểm tra Task PUBLISH sang DONE
        publish_task = Task.objects.get(item=updated_item, role=TaskRole.PUBLISH)
        self.assertEqual(publish_task.status, TaskStatus.DONE)

    def test_record_publication_success_owner(self):
        """
        Chủ workspace có toàn quyền ghi nhận xuất bản thay mặt publisher (Spec 6.1).
        """
        pub_url = "https://facebook.com/mypage/posts/999"
        pub_time = timezone.now()

        pub, updated_item = record_content_publication(
            user=self.owner,
            item=self.item,
            url=pub_url,
            published_at=pub_time,
        )

        self.assertEqual(updated_item.state, ContentItemState.PUBLISHED)
        self.assertEqual(pub.recorded_by, self.owner)
        self.assertEqual(pub.url, pub_url)

    def test_record_publication_forbidden_writer_and_editor(self):
        """
        Người viết và Người biên tập không được phân công xuất bản thì bị từ chối PermissionDenied (Spec 6.1).
        """
        pub_url = "https://facebook.com/test"
        pub_time = timezone.now()

        with self.assertRaises(PermissionDenied):
            record_content_publication(
                user=self.writer,
                item=self.item,
                url=pub_url,
                published_at=pub_time,
            )

        with self.assertRaises(PermissionDenied):
            record_content_publication(
                user=self.editor,
                item=self.item,
                url=pub_url,
                published_at=pub_time,
            )

    def test_record_publication_blocked_item_rejected_ac12(self):
        """
        AC12: Bài bị chặn; thử nộp/duyệt/đăng -> Bị từ chối ValidationError.
        Sau khi giải quyết blocker, ghi nhận xuất bản bình thường.
        """
        block_content_item(
            user=self.owner,
            item=self.item,
            reason="Chờ xác nhận bản quyền hình ảnh",
            expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_blocked)

        with self.assertRaises(ValidationError) as ctx:
            record_content_publication(
                user=self.publisher,
                item=self.item,
                url="https://facebook.com/post/blocked",
                published_at=timezone.now(),
            )
        self.assertIn("đang bị chặn", str(ctx.exception))

        unblock_content_item(
            user=self.owner,
            item=self.item,
            resolution_note="Đã xác nhận bản quyền ảnh hợp lệ",
            expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_blocked)

        pub, updated_item = record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/post/unblocked",
            published_at=timezone.now(),
            expected_row_version=self.item.row_version,
        )
        self.assertEqual(updated_item.state, ContentItemState.PUBLISHED)

    def test_record_publication_invalid_state_rejected(self):
        """
        Chỉ bài viết ở trạng thái READY_TO_PUBLISH mới được xuất bản.
        """
        item_todo = add_content_item(
            user=self.owner,
            package=self.package,
            title="Bài viết #2: Chưa duyệt",
            brief="Brief bài viết nháp.",
            cta="Đăng ký nhận tin",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
            writing_deadline=timezone.now() + datetime.timedelta(days=2),
            editing_deadline=timezone.now() + datetime.timedelta(days=4),
            review_deadline=timezone.now() + datetime.timedelta(days=5),
            planned_publish_at=timezone.now() + datetime.timedelta(days=7),
        )
        self.assertEqual(item_todo.state, ContentItemState.TODO)

        with self.assertRaises(ValidationError) as ctx:
            record_content_publication(
                user=self.publisher,
                item=item_todo,
                url="https://facebook.com/test",
                published_at=timezone.now(),
            )
        self.assertIn("READY_TO_PUBLISH", str(ctx.exception))

    def test_record_publication_no_active_approval_rejected_ac13(self):
        """
        AC13: Ghi nhận đăng thiếu URL hoặc chưa duyệt -> Bị từ chối.
        Nếu Chủ mở lại bài (reopen), approval bị vô hiệu -> không cho đăng dựa trên approval cũ (AC09).
        """
        reopen_content_item(
            user=self.owner,
            item=self.item,
            reason="Cần chỉnh lại câu CTA cuối bài",
            expected_row_version=self.item.row_version,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.state, ContentItemState.EDITING)

        with self.assertRaises(ValidationError):
            record_content_publication(
                user=self.publisher,
                item=self.item,
                url="https://facebook.com/test",
                published_at=timezone.now(),
            )

    def test_record_publication_missing_or_invalid_url_rejected_ac13(self):
        """
        AC13: URL bắt buộc và phải hợp lệ (scheme + netloc).
        """
        with self.assertRaises(ValidationError) as ctx1:
            record_content_publication(
                user=self.publisher,
                item=self.item,
                url="",
                published_at=timezone.now(),
            )
        self.assertIn("URL", str(ctx1.exception))

        with self.assertRaises(ValidationError) as ctx2:
            record_content_publication(
                user=self.publisher,
                item=self.item,
                url="not-a-valid-url",
                published_at=timezone.now(),
            )
        self.assertIn("không hợp lệ", str(ctx2.exception))

    def test_record_publication_missing_published_at_rejected(self):
        """
        Thời điểm xuất bản thực tế là bắt buộc.
        """
        with self.assertRaises(ValidationError):
            record_content_publication(
                user=self.publisher,
                item=self.item,
                url="https://facebook.com/test",
                published_at=None,
            )

    def test_record_publication_idempotency_ac13(self):
        """
        AC13 / Spec 6.3: Idempotency key chống double-click.
        Nếu gửi lặp cùng key trên bài đã đăng, trả về bản ghi publication hiện có, không nhân bản.
        """
        pub1, item1 = record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/post/idemp",
            published_at=timezone.now(),
            expected_row_version=self.item.row_version,
            idempotency_key="key_double_click_123",
        )
        self.assertEqual(ContentPublication.objects.filter(item=self.item).count(), 1)

        pub2, item2 = record_content_publication(
            user=self.publisher,
            item=item1,
            url="https://facebook.com/post/idemp",
            published_at=timezone.now(),
            idempotency_key="key_double_click_123",
        )
        self.assertEqual(pub1.id, pub2.id)
        self.assertEqual(ContentPublication.objects.filter(item=self.item).count(), 1)

    def test_record_publication_occ_conflict_409_ac10(self):
        """
        AC10: Hai người sửa cùng row_version -> người gửi stale expected_row_version nhận 409.
        """
        stale_version = self.item.row_version - 1
        with self.assertRaises(ConcurrencyConflictError):
            record_content_publication(
                user=self.publisher,
                item=self.item,
                url="https://facebook.com/post/stale",
                published_at=timezone.now(),
                expected_row_version=stale_version,
            )

    def test_reopen_and_republish_preserves_publication_history_spec_f06(self):
        """
        Spec F06: Bài đã đăng cần sửa:
        - Chủ mở lại: bản ghi xuất bản cũ VẪN GIỮ TRONG LỊCH SỬ.
        - Lần xác nhận tiếp theo gắn bản được duyệt mới.
        """
        pub_v1, item = record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/post/v1",
            published_at=timezone.now() - datetime.timedelta(hours=2),
            expected_row_version=self.item.row_version,
        )
        self.assertEqual(pub_v1.version.version_no, 1)
        self.assertEqual(ContentPublication.objects.filter(item=item).count(), 1)

        reopen_content_item(
            user=self.owner,
            item=item,
            reason="Cần cập nhật đường link mua hàng mới",
            expected_row_version=item.row_version,
        )
        item.refresh_from_db()
        self.assertEqual(item.state, ContentItemState.EDITING)
        self.assertEqual(ContentPublication.objects.filter(item=item).count(), 1)

        create_editor_version(user=self.editor, item=item, text="Nội dung bài viết v2 đã cập nhật link mới.")
        item.refresh_from_db()
        checklist_ok = {"brief_compliance": True, "factual_accuracy": True, "voice_tone": True, "cta_verified": True}
        submit_for_owner_review(user=self.editor, item=item, checklist=checklist_ok)
        item.refresh_from_db()
        app_v2, item = owner_approve_item(
            user=self.owner,
            item=item,
            expected_version_id=item.latest_version_id,
            expected_row_version=item.row_version,
        )
        self.assertEqual(app_v2.version.version_no, 2)

        pub_v2, item = record_content_publication(
            user=self.publisher,
            item=item,
            url="https://facebook.com/post/v2",
            published_at=timezone.now(),
            expected_row_version=item.row_version,
        )
        self.assertEqual(pub_v2.version.version_no, 2)

        all_pubs = list(ContentPublication.objects.filter(item=item).order_by("recorded_at"))
        self.assertEqual(len(all_pubs), 2)
        self.assertEqual(all_pubs[0].version.version_no, 1)
        self.assertEqual(all_pubs[0].url, "https://facebook.com/post/v1")
        self.assertEqual(all_pubs[1].version.version_no, 2)
        self.assertEqual(all_pubs[1].url, "https://facebook.com/post/v2")

    def test_edit_publication_metadata_success(self):
        """
        Spec F06 & mục 10: Chỉnh sửa nhầm URL / thời điểm đăng:
        - Không mở lại nội dung, không đổi version_id hay approval_id.
        - Bắt buộc có lý do sửa (reason) để lưu audit trail.
        """
        pub, item = record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/original_wrong_link",
            published_at=timezone.now() - datetime.timedelta(hours=1),
            expected_row_version=self.item.row_version,
        )

        new_url = "https://facebook.com/corrected_correct_link"
        new_time = timezone.now() - datetime.timedelta(minutes=30)
        orig_version = pub.version
        orig_approval = pub.approval

        updated_pub = update_publication_metadata(
            user=self.publisher,
            publication=pub,
            url=new_url,
            published_at=new_time,
            reason="Nhập nhầm link của bài trước đó",
        )

        self.assertEqual(updated_pub.url, new_url)
        self.assertEqual(updated_pub.published_at, new_time)
        self.assertEqual(updated_pub.version, orig_version)
        self.assertEqual(updated_pub.approval, orig_approval)

    def test_edit_publication_metadata_missing_reason_rejected(self):
        """
        Sửa metadata bắt buộc phải có lý do sửa để phục vụ audit.
        """
        pub, _ = record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/link1",
            published_at=timezone.now(),
        )

        with self.assertRaises(ValidationError) as ctx:
            update_publication_metadata(
                user=self.publisher,
                publication=pub,
                url="https://facebook.com/link2",
                published_at=timezone.now(),
                reason="",
            )
        self.assertIn("lý do", str(ctx.exception).lower())

    def test_package_completion_ac14_two_published_one_cancelled(self):
        """
        Spec 6.2 & AC14:
        Gói 3 bài: 2 bài đăng, 1 bài hủy -> Gói hoàn thành 2/2 và hiện 1 bài hủy (COMPLETED).
        """
        t_now = timezone.now()

        item2 = add_content_item(
            user=self.owner,
            package=self.package,
            title="Bài viết #2: Khuyến mãi",
            brief="Brief bài viết #2",
            cta="Mua ngay hôm nay",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
            writing_deadline=t_now + datetime.timedelta(days=2),
            editing_deadline=t_now + datetime.timedelta(days=4),
            review_deadline=t_now + datetime.timedelta(days=5),
            planned_publish_at=t_now + datetime.timedelta(days=7),
        )
        item3 = add_content_item(
            user=self.owner,
            package=self.package,
            title="Bài viết #3: Feedback khách hàng",
            brief="Brief bài viết #3",
            cta="Xem thêm cảm nhận",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
            writing_deadline=t_now + datetime.timedelta(days=2),
            editing_deadline=t_now + datetime.timedelta(days=4),
            review_deadline=t_now + datetime.timedelta(days=5),
            planned_publish_at=t_now + datetime.timedelta(days=7),
        )

        record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/post/item1",
            published_at=t_now,
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.status, PackageStatus.ACTIVE)

        start_writing_task(user=self.writer, item=item2)
        submit_content_version(user=self.writer, item=item2, text="Nội dung bài 2")
        item2.refresh_from_db()
        checklist_ok = {"brief_compliance": True, "factual_accuracy": True, "voice_tone": True, "cta_verified": True}
        submit_for_owner_review(user=self.editor, item=item2, checklist=checklist_ok)
        item2.refresh_from_db()
        owner_approve_item(user=self.owner, item=item2, expected_version_id=item2.latest_version_id, expected_row_version=item2.row_version)
        item2.refresh_from_db()
        record_content_publication(
            user=self.publisher,
            item=item2,
            url="https://facebook.com/post/item2",
            published_at=t_now,
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.status, PackageStatus.ACTIVE)

        cancel_content_item(
            user=self.owner,
            item=item3,
            reason="Thay đổi kế hoạch nội dung quý, hủy bài 3",
            expected_row_version=item3.row_version,
        )
        item3.refresh_from_db()
        self.assertEqual(item3.state, ContentItemState.CANCELLED)

        # GÓI TỰ ĐỘNG CHUYỂN COMPLETED (AC14)
        self.package.refresh_from_db()
        self.assertEqual(self.package.status, PackageStatus.COMPLETED)

    def test_package_completion_ac14_all_three_cancelled_not_completed(self):
        """
        Spec 6.2 & AC14:
        Cả 3 bài bị hủy -> Gói KHÔNG hiện hoàn thành.
        """
        t_now = timezone.now()

        item2 = add_content_item(
            user=self.owner,
            package=self.package,
            title="Bài 2",
            brief="Brief 2",
            cta="CTA bài 2",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
            writing_deadline=t_now + datetime.timedelta(days=2),
            editing_deadline=t_now + datetime.timedelta(days=4),
            review_deadline=t_now + datetime.timedelta(days=5),
            planned_publish_at=t_now + datetime.timedelta(days=7),
        )
        item3 = add_content_item(
            user=self.owner,
            package=self.package,
            title="Bài 3",
            brief="Brief 3",
            cta="CTA bài 3",
            writer_membership=self.writer_membership,
            editor_membership=self.editor_membership,
            publisher_membership=self.publisher_membership,
            writing_deadline=t_now + datetime.timedelta(days=2),
            editing_deadline=t_now + datetime.timedelta(days=4),
            review_deadline=t_now + datetime.timedelta(days=5),
            planned_publish_at=t_now + datetime.timedelta(days=7),
        )

        cancel_content_item(user=self.owner, item=self.item, reason="Hủy bài 1", expected_row_version=self.item.row_version)
        cancel_content_item(user=self.owner, item=item2, reason="Hủy bài 2", expected_row_version=item2.row_version)
        cancel_content_item(user=self.owner, item=item3, reason="Hủy bài 3", expected_row_version=item3.row_version)

        self.package.refresh_from_db()
        self.assertNotEqual(self.package.status, PackageStatus.COMPLETED)

    def test_package_reverts_to_active_on_reopen_spec_6_2(self):
        """
        Spec 6.2: Mở lại bài làm gói COMPLETED trở lại ACTIVE.
        """
        record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/post/single",
            published_at=timezone.now(),
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.status, PackageStatus.COMPLETED)

        self.item.refresh_from_db()
        reopen_content_item(
            user=self.owner,
            item=self.item,
            reason="Mở lại bài duy nhất để sửa đổi",
            expected_row_version=self.item.row_version,
        )

        self.package.refresh_from_db()
        self.assertEqual(self.package.status, PackageStatus.ACTIVE)

    def test_view_record_publication_http_post(self):
        """
        Kiểm thử View HTTP POST ContentItemRecordPublicationView:
        - Thành công: redirect về item_detail kèm flash message tiếng Việt.
        - Thiếu URL: trả về 400 và giữ nguyên form.
        - Lệch row_version: trả về 409 ConcurrencyConflictError.
        """
        url = reverse("workspaces:item_record_publication", kwargs={
            "workspace_id": self.workspace.id,
            "package_id": self.package.id,
            "item_id": self.item.id,
        })

        resp_invalid = self.client_publisher.post(url, {
            "url": "",
            "published_at": "2026-10-14T10:00",
            "expected_row_version": self.item.row_version,
        })
        self.assertEqual(resp_invalid.status_code, 400)
        self.assertContains(resp_invalid, "Bắt buộc nhập URL", status_code=400)

        resp_conflict = self.client_publisher.post(url, {
            "url": "https://facebook.com/post/occ",
            "published_at": "2026-10-14T10:00",
            "expected_row_version": self.item.row_version + 99,
        })
        self.assertEqual(resp_conflict.status_code, 409)

        resp_success = self.client_publisher.post(url, {
            "url": "https://facebook.com/post/valid",
            "published_at": "2026-10-14T10:00",
            "expected_row_version": self.item.row_version,
            "idempotency_key": "view_pub_test_1",
        })
        self.assertEqual(resp_success.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.state, ContentItemState.PUBLISHED)

    def test_view_edit_publication_metadata_http_post(self):
        """
        Kiểm thử View HTTP POST ContentPublicationEditView:
        - Sửa metadata thành công, redirect và có flash message.
        """
        pub, item = record_content_publication(
            user=self.publisher,
            item=self.item,
            url="https://facebook.com/old_url",
            published_at=timezone.now(),
        )

        edit_url = reverse("workspaces:publication_edit_metadata", kwargs={
            "workspace_id": self.workspace.id,
            "package_id": self.package.id,
            "item_id": item.id,
            "publication_id": pub.id,
        })

        resp = self.client_publisher.post(edit_url, {
            "url": "https://facebook.com/new_updated_url",
            "published_at": "2026-10-14T12:00",
            "reason": "Sửa nhầm URL do paste sai link",
        })
        self.assertEqual(resp.status_code, 302)

        pub.refresh_from_db()
        self.assertEqual(pub.url, "https://facebook.com/new_updated_url")

