import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import AccountEmailIdentity
from apps.workspaces.models import (
    AccessRole,
    BrandProfile,
    EmploymentType,
    Membership,
    MembershipStatus,
    Workspace,
)
from apps.workspaces.selectors import get_brand_profile
from apps.workspaces.services import (
    ConcurrencyConflictError,
    create_workspace_with_owner,
    save_brand_profile,
)

User = get_user_model()


class BrandProfileMilestoneB03Tests(TestCase):
    def setUp(self):
        # 1. Owner User
        self.owner = User.objects.create_user(
            username="owner_user",
            email="owner@example.com",
            password="StrongPassword123!",
        )
        self.owner.email_identity.mark_as_verified()

        # 2. Member User
        self.member = User.objects.create_user(
            username="member_user",
            email="member@example.com",
            password="StrongPassword123!",
        )
        self.member.email_identity.mark_as_verified()

        # 3. Outsider User (Không thuộc workspace)
        self.outsider = User.objects.create_user(
            username="outsider_user",
            email="outsider@example.com",
            password="StrongPassword123!",
        )
        self.outsider.email_identity.mark_as_verified()

        # 4. Workspace 1 & Membership
        self.workspace = create_workspace_with_owner(
            user=self.owner,
            name="SaaS Content Marketing Studio",
            timezone_str="Asia/Ho_Chi_Minh",
        )
        self.member_membership = Membership.objects.create(
            workspace=self.workspace,
            user=self.member,
            access_role=AccessRole.MEMBER,
            employment_type=EmploymentType.IN_HOUSE,
            status=MembershipStatus.ACTIVE,
            ai_use_allowed=True,
        )

        # 5. Workspace 2 (Khác chủ - Dùng để test cách ly tenant)
        self.other_owner = User.objects.create_user(
            username="other_owner",
            email="other_owner@example.com",
            password="StrongPassword123!",
        )
        self.other_owner.email_identity.mark_as_verified()
        self.other_workspace = create_workspace_with_owner(
            user=self.other_owner,
            name="Other Enterprise Workspace",
            timezone_str="UTC",
        )

        self.client = Client()

    def test_database_test_isolation(self):
        """Xác nhận test runner chạy trên database test độc lập (test_postgres)."""
        db_name = connection.settings_dict.get("NAME")
        self.assertTrue(
            "test" in db_name.lower(),
            f"Test phải chạy trên database test tách biệt. Hiện tại: {db_name}",
        )

    def test_brand_profile_creation_and_auto_revision(self):
        """Khởi tạo lần đầu: revision = 1; lưu lần tiếp theo: revision tăng +1 tuần tự."""
        profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="SaaS Master",
            product_summary="Nền tảng quản lý ban content marketing B2B",
            target_audience="Chủ doanh nghiệp nhỏ và Freelance Content Marketer",
            tone_of_voice="Chuyên nghiệp, thẳng thắn, truyền cảm hứng",
            avoid_guidelines="Không giật tít vô căn cứ, không dùng từ ngữ sáo rỗng",
            allowed_claims="Tiết kiệm 50% thời gian điều phối duyệt bài",
            source_urls=["https://saas-master.example.com/docs"],
        )

        self.assertEqual(profile.revision, 1)
        self.assertEqual(profile.updated_by, self.owner)
        self.assertEqual(profile.name, "SaaS Master")

        updated_profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="SaaS Master v2",
            product_summary="Nền tảng quản lý ban content marketing nâng cao",
            target_audience="Doanh nghiệp SME và Agencies",
            expected_revision=1,
        )

        self.assertEqual(updated_profile.revision, 2)
        self.assertEqual(updated_profile.name, "SaaS Master v2")
        self.assertEqual(updated_profile.product_summary, "Nền tảng quản lý ban content marketing nâng cao")

    def test_brand_profile_one_to_one_constraint(self):
        """Mỗi workspace chỉ có đúng duy nhất một BrandProfile (OneToOne unique constraint)."""
        BrandProfile.objects.create(
            workspace=self.workspace,
            name="Brand 1",
            product_summary="Sản phẩm 1",
            target_audience="Khách 1",
            revision=1,
        )

        with self.assertRaises(IntegrityError):
            BrandProfile.objects.create(
                workspace=self.workspace,
                name="Brand 2",
                product_summary="Sản phẩm 2",
                target_audience="Khách 2",
                revision=1,
            )
    def test_brand_profile_field_validations(self):
        """Kiểm tra giới hạn ký tự và ràng buộc dữ liệu theo Spec mục 4."""
        # 1. Tên rỗng hoặc quá 100 ký tự
        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="   ",
                product_summary="SP",
                target_audience="KH",
            )
            p.full_clean()

        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="A" * 101,
                product_summary="SP",
                target_audience="KH",
            )
            p.full_clean()

        # 2. Sản phẩm rỗng hoặc quá 5000 ký tự
        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="   ",
                target_audience="KH",
            )
            p.full_clean()

        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="A" * 5001,
                target_audience="KH",
            )
            p.full_clean()

        # 3. Đối tượng rỗng hoặc quá 3000 ký tự
        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="SP",
                target_audience="   ",
            )
            p.full_clean()

        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="SP",
                target_audience="A" * 3001,
            )
            p.full_clean()

    def test_source_urls_validation_https_and_max_ten(self):
        """URL nguồn tham khảo: chỉ chấp nhận HTTPS, tối đa 10 URL, chặn HTTP và scheme khác."""
        # 1. Chặn HTTP (chỉ chấp nhận HTTPS)
        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="SP",
                target_audience="KH",
                source_urls=["http://example.com/not-https"],
            )
            p.full_clean()

        # 2. Chặn URL không hợp lệ
        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="SP",
                target_audience="KH",
                source_urls=["https://"],
            )
            p.full_clean()

        # 3. Chặn vượt quá 10 URL
        eleven_urls = [f"https://example.com/doc/{i}" for i in range(11)]
        with self.assertRaises(ValidationError):
            p = BrandProfile(
                workspace=self.other_workspace,
                name="Valid Name",
                product_summary="SP",
                target_audience="KH",
                source_urls=eleven_urls,
            )
            p.full_clean()

        # 4. Hợp lệ 10 URL HTTPS
        ten_urls = [f"https://example.com/doc/{i}" for i in range(10)]
        valid_profile = BrandProfile(
            workspace=self.other_workspace,
            name="Valid Name",
            product_summary="SP",
            target_audience="KH",
            source_urls=ten_urls,
        )
        valid_profile.full_clean()
        self.assertEqual(len(valid_profile.source_urls), 10)

    def test_immutable_snapshot_behavior(self):
        """AC15 & Spec F02: Snapshot thương hiệu không tự thay đổi khi BrandProfile được sửa đổi sau đó."""
        profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Original Brand",
            product_summary="Sản phẩm ban đầu",
            target_audience="Đối tượng ban đầu",
            tone_of_voice="Tone ban đầu",
            source_urls=["https://example.com/origin"],
        )

        # Trích xuất snapshot tại rev 1
        snapshot = profile.to_snapshot()
        self.assertEqual(snapshot["brand_name"], "Original Brand")
        self.assertEqual(snapshot["revision"], 1)

        # Chủ chỉnh sửa profile lên rev 2
        updated_profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Updated Brand 2",
            product_summary="Sản phẩm mới",
            target_audience="Đối tượng mới",
            expected_revision=1,
        )
        self.assertEqual(updated_profile.revision, 2)

        # Snapshot cũ đã trích xuất phải giữ nguyên giá trị không thay đổi
        self.assertEqual(snapshot["brand_name"], "Original Brand")
        self.assertEqual(snapshot["revision"], 1)
        self.assertEqual(snapshot["product_summary"], "Sản phẩm ban đầu")
    def test_optimistic_concurrency_conflict(self):
        """AC10: Gửi expected_revision sai trả về ConcurrencyConflictError (HTTP 409) và không mất dữ liệu."""
        profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Brand Concurrent",
            product_summary="Sản phẩm Concurrent",
            target_audience="Khách Concurrent",
        )
        self.assertEqual(profile.revision, 1)

        # 1. Tầng Service: ném ConcurrencyConflictError
        with self.assertRaises(ConcurrencyConflictError):
            save_brand_profile(
                user=self.owner,
                workspace=self.workspace,
                name="Brand Conflict Attempt",
                product_summary="Sản phẩm Conflict",
                target_audience="Khách Conflict",
                expected_revision=999,  # Lệch revision hiện tại (1)
            )

        # 2. Tầng View: Nhận HTTP 409 và form giữ nguyên dữ liệu
        self.client.force_login(self.owner)
        url = reverse("workspaces:brand_profile", kwargs={"workspace_id": self.workspace.id})
        response = self.client.post(
            url,
            {
                "name": "Brand Form Conflict",
                "product_summary": "Nội dung form đã nhập",
                "target_audience": "Khách hàng form",
                "expected_revision": 999,  # Lệch revision
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Xung đột phiên bản", status_code=409)
        # Kiểm tra dữ liệu trong CSDL vẫn giữ nguyên phiên bản 1
        profile.refresh_from_db()
        self.assertEqual(profile.revision, 1)
        self.assertEqual(profile.name, "Brand Concurrent")

    def test_permission_matrix_and_tenant_isolation(self):
        """Ma trận phân quyền B03: Chủ xem/sửa, Thành viên chỉ xem (POST 403), Người ngoài nhận 404."""
        # Tạo BrandProfile ban đầu
        save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Brand Studio",
            product_summary="Sản phẩm Studio",
            target_audience="Khách Studio",
            tone_of_voice="Chuyên nghiệp",
        )

        url = reverse("workspaces:brand_profile", kwargs={"workspace_id": self.workspace.id})

        # 1. Khách vãng lai chưa đăng nhập -> redirect login
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

        # 2. Thành viên (MEMBER)
        self.client.force_login(self.member)
        # GET thành công (200), giao diện chỉ đọc
        resp_member_get = self.client.get(url)
        self.assertEqual(resp_member_get.status_code, 200)
        self.assertContains(resp_member_get, "Chế độ chỉ đọc")
        self.assertContains(resp_member_get, "Brand Studio")
        # MEMBER POST cố tình sửa -> 403 Forbidden
        resp_member_post = self.client.post(
            url,
            {
                "name": "Hacked Brand",
                "product_summary": "Hacked",
                "target_audience": "Hacked",
            },
        )
        self.assertEqual(resp_member_post.status_code, 403)

        # 3. Người ngoài workspace (OUTSIDER) -> 404 Not Found (Spec 3.1)
        self.client.force_login(self.outsider)
        resp_outsider_get = self.client.get(url)
        self.assertEqual(resp_outsider_get.status_code, 404)
        resp_outsider_post = self.client.post(
            url,
            {
                "name": "Outsider Edit",
                "product_summary": "Outsider",
                "target_audience": "Outsider",
            },
        )
        self.assertEqual(resp_outsider_post.status_code, 404)

        # 4. Thành viên bị vô hiệu hóa (INACTIVE) -> 404 Not Found
        self.member_membership.status = MembershipStatus.INACTIVE
        self.member_membership.save(update_fields=["status"])
        self.client.force_login(self.member)
        resp_inactive_get = self.client.get(url)
        self.assertEqual(resp_inactive_get.status_code, 404)

        # 5. Chủ workspace (OWNER)
        self.client.force_login(self.owner)
        resp_owner_get = self.client.get(url)
        self.assertEqual(resp_owner_get.status_code, 200)
        self.assertContains(resp_owner_get, "Cập nhật thông tin thương hiệu")

        resp_owner_post = self.client.post(
            url,
            {
                "name": "Brand Studio Updated",
                "product_summary": "Sản phẩm Studio Mới",
                "target_audience": "Khách Studio Mới",
                "expected_revision": 1,
            },
        )
        self.assertEqual(resp_owner_post.status_code, 302)
        # Xác nhận redirect về lại trang brand
        self.assertEqual(resp_owner_post.url, url)

        # Kiểm tra CSDL cập nhật lên revision 2
        profile = get_brand_profile(self.workspace)
        self.assertEqual(profile.revision, 2)
        self.assertEqual(profile.name, "Brand Studio Updated")
        self.assertEqual(profile.updated_by, self.owner)

    def test_form_validation_and_retains_input_on_error(self):
        """Form validation lỗi trả về 400 và giữ nguyên dữ liệu người dùng đã nhập."""
        self.client.force_login(self.owner)
        url = reverse("workspaces:brand_profile", kwargs={"workspace_id": self.workspace.id})

        # Gửi dữ liệu thiếu trường bắt buộc
        response = self.client.post(
            url,
            {
                "name": "Valid Brand Name",
                "product_summary": "",  # Thiếu trường bắt buộc
                "target_audience": "Khách hàng mục tiêu hợp lệ",
                "source_urls": "https://example.com/doc1",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Thông tin sản phẩm/dịch vụ không được để trống.", status_code=400)
        # Kiểm tra dữ liệu đã nhập vẫn nằm trong form render
        self.assertContains(response, "Valid Brand Name", status_code=400)
        self.assertContains(response, "Khách hàng mục tiêu hợp lệ", status_code=400)

    def test_admin_brand_profile_registration(self):
        """Kiểm tra model BrandProfile được đăng ký trong Django Admin với readonly fields."""
        from django.contrib.admin.sites import site
        self.assertIn(BrandProfile, site._registry)
        admin_instance = site._registry[BrandProfile]
        self.assertIn("revision", admin_instance.readonly_fields)
        self.assertIn("id", admin_instance.readonly_fields)

    def test_concurrent_brand_profile_first_creation(self):
        """
        Gate B03: Hai request cùng tạo BrandProfile lần đầu.
        Nhờ khóa Workspace và xử lý ConcurrencyConflictError, chỉ đúng 1 profile được tạo (rev 1),
        request thứ hai không gây lỗi 500 ngoài ý muốn mà được xử lý thành ConcurrencyConflictError rõ ràng.
        """
        # Workspace này chưa có profile
        self.assertIsNone(get_brand_profile(self.other_workspace))

        # Request 1 tạo thành công
        p1 = save_brand_profile(
            user=self.other_owner,
            workspace=self.other_workspace,
            name="Brand Concurrent 1",
            product_summary="Sản phẩm 1",
            target_audience="Khách hàng 1",
            expected_revision=0,
        )
        self.assertEqual(p1.revision, 1)

        # Request 2 gửi expected_revision=0 khi profile đã được tạo
        with self.assertRaises(ConcurrencyConflictError):
            save_brand_profile(
                user=self.other_owner,
                workspace=self.other_workspace,
                name="Brand Concurrent 2",
                product_summary="Sản phẩm 2",
                target_audience="Khách hàng 2",
                expected_revision=0,
            )

        # Đảm bảo trong CSDL chỉ có đúng 1 profile duy nhất
        self.assertEqual(BrandProfile.objects.filter(workspace=self.other_workspace).count(), 1)

    def test_snapshot_deep_isolation_with_mutable_data(self):
        """
        Gate B03: Snapshot độc lập hoàn toàn với BrandProfile gốc, bao gồm dữ liệu mutable như source_urls.
        Sửa đổi profile, sửa đổi danh sách URL, hoặc sửa đổi chính snapshot không làm thay đổi chéo.
        """
        initial_urls = ["https://example.com/api/v1", "https://example.com/docs"]
        profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Original Snapshot Brand",
            product_summary="Sản phẩm snapshot",
            target_audience="Khách hàng snapshot",
            source_urls=initial_urls,
        )

        snapshot_1 = profile.to_snapshot()
        self.assertEqual(snapshot_1["source_urls"], initial_urls)
        self.assertEqual(snapshot_1["revision"], 1)

        # 1. Thao tác mutable trên list của snapshot_1 không ảnh hưởng tới profile
        snapshot_1["source_urls"].append("https://malicious-injection.com")
        self.assertNotIn("https://malicious-injection.com", profile.source_urls)

        # 2. Cập nhật profile lên revision 2 với URL mới
        updated_urls = ["https://example.com/v2-new"]
        updated_profile = save_brand_profile(
            user=self.owner,
            workspace=self.workspace,
            name="Updated Brand Rev 2",
            product_summary="Sản phẩm mới rev 2",
            target_audience="Khách hàng mới rev 2",
            source_urls=updated_urls,
            expected_revision=1,
        )
        self.assertEqual(updated_profile.revision, 2)
        self.assertEqual(updated_profile.source_urls, updated_urls)

        # 3. Snapshot 1 ban đầu vẫn giữ nguyên vẹn giá trị ban đầu (trừ phần tử do snapshot_1 tự sửa ở bước 1)
        self.assertEqual(snapshot_1["brand_name"], "Original Snapshot Brand")
        self.assertEqual(snapshot_1["revision"], 1)
        self.assertEqual(snapshot_1["product_summary"], "Sản phẩm snapshot")
        self.assertEqual(snapshot_1["source_urls"][:2], initial_urls)
        self.assertNotIn("https://example.com/v2-new", snapshot_1["source_urls"])



