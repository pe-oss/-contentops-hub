# SPEC TRIỂN KHAI — BAN CONTENT MARKETING

**Dự án:** SaaS-mini-001  
**Phiên bản:** 1.1 · 12/10/2026 — điều chỉnh theo boilerplate GitHub  
**Trạng thái:** Bản triển khai đề xuất; chưa triển khai phần mềm.  
**Đối tượng đọc:** Chủ sản phẩm, thiết kế, lập trình và kiểm thử.

## 1. Quyết định phạm vi

Sản phẩm giúp Chủ doanh nghiệp một người hoặc doanh nghiệp nhỏ vận hành Ban Content Marketing: giao mục tiêu, phân công, theo dõi, duyệt và ghi nhận xuất bản. Chủ có thể tự làm, thuê freelancer, thuê nhân sự cố định hoặc dùng AI hỗ trợ. Không buộc khách hàng dùng AI.

Các quyết định đã có từ trao đổi: bốn vị trí điều phối, viết, biên tập, xuất bản; luôn có người chịu trách nhiệm; hỗ trợ AI bên ngoài; BYOK là kết nối AI tùy chọn; không tự đăng bài trong bản đầu; duyệt một phiên bản cố định.

Các mặc định do bản Spec này đề xuất để có thể lập trình:

| Quyết định | Mặc định triển khai |
|---|---|
| R1 — bản lõi | Đủ luồng con người và AI bên ngoài; không phụ thuộc API AI |
| R1.1 — phần mở rộng BYOK | Phát triển sau khi luồng lõi qua nghiệm thu; bật bằng feature flag |
| Kênh, định dạng R1 | Một kênh Facebook, bài văn bản; không tạo/lưu tệp media |
| Doanh nghiệp | Một workspace có một Chủ, một hồ sơ thương hiệu; thành viên có thể thuộc nhiều workspace |
| Duyệt | Chủ duyệt kế hoạch và nội dung cuối cùng; chưa ủy quyền duyệt |
| Công cụ biên soạn | Ô nhập văn bản đơn giản, không làm trình soạn thảo cộng tác |
| Tham gia workspace | Đăng nhập và nhận lời mời qua link do Chủ tự gửi; không xây email nghiệp vụ; email xác minh tài khoản là phần hạ tầng xác thực riêng |
| Thương mại | Chủ sản phẩm quyết định giá sau; BILLING_ENABLED=False ở R1/R1.1, không kế thừa giá mẫu hoặc Free/Pro thành định giá sản phẩm |
| Công nghệ | Python 3.12, Django 5.2 LTS, Django Templates + HTMX 2.x + CSS/JS sẵn có; PostgreSQL cho staging/pilot/production; Gunicorn + WhiteNoise; xem mục 17–19 |

Đây là mặc định thiết kế, không phải các quyết định người dùng đã xác nhận riêng từng mục. Thay đổi mặc định cần cập nhật Spec và tác động tới backlog.

## 2. Mục tiêu và ngoài phạm vi

**Công việc cần giải quyết:** Chủ chuyển một mục tiêu nội dung thành các bài đã được kiểm tra, duyệt và ghi nhận xuất bản; nhìn được việc cần mình quyết định mà không hỏi tiến độ từng người.

**Kết quả sản phẩm phải tạo:** kế hoạch, nhiệm vụ có trách nhiệm, bản bàn giao, lịch sử quyết định và liên kết xuất bản. Không coi phần trăm tiến độ là bằng chứng đã làm việc.

**Ngoài R1/R1.1:** tích hợp Zalo/Messenger, tự đăng Facebook, lấy dữ liệu mạng xã hội, ảnh/video, AI tự vận hành nhiều bước, thanh toán freelancer, lương/hợp đồng, CRM, doanh thu từ content, quản lý các ban khác, chat thời gian thực, bình luận theo từng đoạn, tự đọc Google Docs, tự xác minh URL bài đăng.

**Giả thuyết:** giảm công điều phối đủ để người dùng tiếp tục sử dụng. Chưa có bằng chứng về nhu cầu trả tiền hoặc ưu thế so với thị trường.

## 3. Thuật ngữ và phân quyền

- Workspace: không gian dữ liệu của một doanh nghiệp.
- Gói content: tập bài phục vụ một mục tiêu, một khoảng thời gian, một kênh.
- Bài: đơn vị nội dung, có nhiều phiên bản và một vòng đời.
- Vị trí: trách nhiệm nghề nghiệp; không đồng nghĩa quyền quản trị.
- Phân công: người đảm nhiệm một vị trí ở gói hoặc bài.
- Phiên bản: bản nội dung được lưu cố định; sửa tạo bản mới.
- Cách thực hiện: MANUAL, EXTERNAL_AI hoặc BYOK. AI bên ngoài không là tài khoản hệ thống.

### 3.1 Vai trò truy cập

OWNER là Chủ workspace. MEMBER là nhân viên hoặc freelancer; employment_type chỉ mô tả quan hệ làm việc, không tự cấp quyền. Quyền làm việc đến từ phân công trong từng gói/bài. Một người có thể giữ nhiều vị trí; Chủ có thể tự giữ tất cả.

| Hành động | Chủ | Điều phối được gán cho gói | Người được gán cho bài |
|---|---|---|---|
| Mời, thu hồi thành viên; sửa thương hiệu | Có | Không | Không |
| Tạo, lưu trữ gói; chỉ định điều phối | Có | Không | Không |
| Sửa kế hoạch nháp, phân công người đang là thành viên | Có | Trong gói phụ trách | Không |
| Duyệt hoặc thay đổi kế hoạch đã duyệt | Có | Chỉ đề nghị Chủ | Không |
| Đọc dữ liệu | Toàn workspace | Gói được giao | Bài được giao và brief/snapshot cần thiết |
| Viết, nộp bản | Có | Chỉ khi kiêm vị trí viết/biên tập | Theo vị trí viết/biên tập |
| Biên tập, chuyển chờ Chủ duyệt | Có | Chỉ khi kiêm biên tập | Biên tập được gán |
| Duyệt bản cuối, mở lại bài | Có | Không | Không |
| Ghi nhận đã đăng | Có | Chỉ khi kiêm xuất bản | Xuất bản được gán |
| Quản lý API key | Có | Không | Không |
| Chạy BYOK | Có | Không mặc định | Viết/biên tập, được Chủ cấp quyền riêng |

Mọi API kiểm tra quyền tại backend theo workspace, đối tượng và hành động; không chỉ ẩn nút. Với đối tượng ngoài phạm vi đọc trả 404. Với đối tượng được đọc nhưng không được sửa trả 403. Điều phối không được cấp quyền AI hoặc tự mở rộng quyền truy cập ngoài gói.

### 3.2 Lời mời và thu hồi

Chủ tạo lời mời gắn email, link hết hạn sau 7 ngày, dùng một lần, token lưu dạng hash. Người nhận đăng nhập với email đã xác minh trùng lời mời mới được chấp nhận. Chủ tự sao chép link để gửi. Không có link truy cập công khai vào bài.

Thu hồi thành viên vô hiệu hóa quyền ở yêu cầu kế tiếp, không xóa tác giả/lịch sử cũ. Nếu còn nhiệm vụ đang mở, Chủ phải chọn người thay thế hoặc tạm chuyển trách nhiệm cho chính mình trong cùng giao dịch.

## 4. Dữ liệu nhập và giới hạn R1

Các giới hạn dưới đây là mặc định kỹ thuật có thể cấu hình; UI và backend cùng kiểm tra. Chuỗi dùng Unicode, loại khoảng trắng đầu/cuối, không chấp nhận nội dung chỉ gồm khoảng trắng. Thời gian lưu UTC, hiển thị theo workspace; mặc định Asia/Ho_Chi_Minh.

| Biểu mẫu | Trường bắt buộc | Trường tùy chọn / kiểm tra |
|---|---|---|
| Workspace | Tên 1–100 ký tự, timezone | Một Chủ duy nhất |
| Thương hiệu | Tên 1–100; sản phẩm 1–5.000; đối tượng 1–3.000 | Giọng văn, điều tránh, tuyên bố được phép: mỗi trường ≤3.000; tối đa 10 URL nguồn |
| Gói content | Tên 1–150; mục tiêu 1–3.000; ngày bắt đầu/kết thúc; điều phối | Ngày kết thúc không trước bắt đầu; kênh cố định FACEBOOK |
| Bài trong kế hoạch | Tiêu đề 1–200; brief 1–5.000; hạn viết; hạn biên tập; hạn duyệt; giờ dự kiến đăng | CTA ≤500; 3 người viết/biên tập/xuất bản, có thể trùng; tối đa 50 bài/gói |
| Nộp phiên bản | Văn bản 1–30.000; nguồn MANUAL/EXTERNAL_AI/BYOK | Tối đa 10 URL làm việc/tham khảo; ghi chú ≤2.000 |
| Yêu cầu sửa / bị chặn | Lý do 1–2.000 | Chọn người cần phản hồi khi bị chặn |
| Ghi nhận xuất bản | URL HTTPS; thời điểm đã đăng không ở tương lai | Gắn phiên bản đã duyệt; ghi chú nếu URL không thuộc Facebook |

Kế hoạch nháp có thể chưa đủ trường. Duyệt kế hoạch phải có đủ người thực hiện đang hoạt động và hạn theo thứ tự viết ≤ biên tập ≤ duyệt ≤ đăng; lịch bài nằm trong khoảng gói. Hạn quá khứ được cảnh báo, Chủ có thể xác nhận giữ để nhập dự án đang chạy.

URL chỉ lưu và mở theo thao tác người dùng, không tự tải nội dung phía server. Chặn scheme khác HTTPS. Link không chứng minh nội dung hoặc quyền truy cập; UI ghi rõ bản văn bản trong SaaS là bản dùng để duyệt.

## 5. Luồng nghiệp vụ chi tiết

### F01 — Thiết lập

Chủ đăng nhập → tạo workspace → điền thương hiệu → tự đảm nhiệm hoặc mời thành viên → tạo gói. Thiếu thành viên không chặn thử nghiệm: các vị trí có thể gán cho Chủ.

### F02 — Kế hoạch

Chủ tạo gói và chỉ định điều phối. Điều phối thêm bài, brief, lịch và phân công. Chủ xem tổng thể, duyệt kế hoạch. Khi duyệt, hệ thống lưu snapshot kế hoạch và thông tin thương hiệu; tạo nhiệm vụ viết, biên tập, xuất bản cho từng bài. Kế hoạch chưa duyệt không cho nộp bài hoặc chạy BYOK.

Sau duyệt, chỉ Chủ sửa phạm vi/brief/lịch. Thay đổi tăng plan_revision và ghi lý do. Đổi deadline/phân công không tự hủy duyệt nội dung. Đổi brief/thông tin áp dụng cho một bài đã duyệt phải mở lại bài đó, hủy hiệu lực duyệt hiện tại. Thay hồ sơ thương hiệu chung không âm thầm đổi snapshot của gói cũ. Chủ phải chủ động áp dụng lại và chọn các bài bị ảnh hưởng.

### F03 — Viết bằng người hoặc AI bên ngoài

Người viết mở Việc của tôi → nhận việc → xem brief/snapshot thương hiệu → tự viết hoặc sao chép brief sang AI riêng → dán kết quả → lưu bản nháp → nộp biên tập.

Sao chép brief dùng template gồm mục tiêu, đối tượng, giọng văn, yêu cầu bài, điều tránh, định dạng đầu ra và yêu cầu đánh dấu thông tin chưa biết. Không tự chuyển dữ liệu sang công cụ AI bên ngoài. Không có API key vẫn dùng đủ F01–F07.

### F04 — Biên tập

Biên tập xem phiên bản được nộp → kiểm tra đúng brief, độ chính xác theo tài liệu, giọng văn và CTA → yêu cầu người viết sửa hoặc tạo phiên bản chỉnh sửa → đánh dấu checklist và chuyển Chủ duyệt. Checklist không bảo đảm dữ kiện đúng; người biên tập chịu trách nhiệm kiểm tra.

### F05 — Duyệt

Chủ xem bản cố định và lịch sử → duyệt hoặc yêu cầu sửa, chọn trả về viết/biên tập. Yêu cầu sửa bắt buộc có lý do. Duyệt ghi người, thời điểm và version_id, không ghi duyệt cho URL có thể thay đổi.

Bản đã gửi Chủ không cho sửa tại chỗ. Muốn sửa phải rút khỏi chờ duyệt theo lệnh Chủ hoặc biên tập, có lý do và thông báo, sau đó tạo phiên bản mới. Không cho phê duyệt nếu màn hình đang xem bản cũ.

### F06 — Xuất bản

Người xuất bản sao chép đúng bản được duyệt → đăng thủ công → nhập URL/thời điểm và xác nhận dùng phiên bản đó. SaaS ghi “Đã đăng — do [người] xác nhận”; không tuyên bố đã kiểm chứng Facebook.

Nếu người xuất bản sửa nội dung, phải đề nghị mở lại để duyệt bản mới. Bài đã đăng cần sửa: Chủ mở lại, bản ghi xuất bản cũ vẫn giữ trong lịch sử; lần xác nhận tiếp theo gắn bản được duyệt mới. Chỉ sửa nhầm URL/thời điểm không mở lại nội dung, nhưng phải có lý do và audit.

### F07 — Ngoại lệ

Người thực hiện báo bị chặn cùng lý do/người cần xử lý. Chủ hoặc người đang chịu trách nhiệm bước đó giải quyết, ghi cách xử lý rồi bỏ chặn. Chủ đổi người, hạn hoặc hủy bài khi cần; tất cả có lịch sử. Không tự coi AI lỗi là công việc đã hoàn tất.

## 6. Máy trạng thái và tính nhất quán

### 6.1 Trạng thái bài

| Từ | Lệnh / điều kiện | Đến | Người có quyền |
|---|---|---|---|
| TODO | Bắt đầu, kế hoạch đã duyệt | WRITING | Người viết hoặc Chủ |
| WRITING | Nộp version có nội dung | EDITING | Người viết hoặc Chủ |
| EDITING | Trả sửa, có lý do | WRITING | Biên tập hoặc Chủ |
| EDITING | Checklist hoàn tất, version được chọn là mới nhất | OWNER_REVIEW | Biên tập hoặc Chủ |
| OWNER_REVIEW | Yêu cầu sửa và chỉ định bước | WRITING / EDITING | Chủ |
| OWNER_REVIEW | Rút gửi duyệt có lý do | EDITING | Biên tập hoặc Chủ |
| OWNER_REVIEW | Duyệt đúng version và revision hiện tại | READY_TO_PUBLISH | Chủ |
| READY_TO_PUBLISH | Ghi nhận đăng bản được duyệt | PUBLISHED | Xuất bản hoặc Chủ |
| READY_TO_PUBLISH / PUBLISHED | Mở lại có lý do, vô hiệu duyệt hiện tại | EDITING | Chủ |
| TODO / WRITING / EDITING / OWNER_REVIEW | Hủy có lý do | CANCELLED | Chủ |
| READY_TO_PUBLISH | Thu hồi duyệt và hủy có lý do | CANCELLED | Chủ |

PUBLISHED không hủy/xóa lịch sử. CANCELLED là trạng thái kết thúc ở R1; cần làm lại thì tạo bài mới. Bài hủy không tính vào mẫu số tiến độ nhưng luôn hiển thị số lượng hủy.

BLOCKED là cờ kèm nguyên nhân và trạng thái gốc, không phải bước riêng. Không cho chuyển tiếp/nộp/duyệt/đăng khi đang bị chặn; vẫn cho lưu nháp, phản hồi, đổi phân công, gỡ chặn hoặc hủy. “Cần sửa” là nhãn đi cùng quyết định trả về bước viết/biên tập, không tạo trạng thái mơ hồ.

### 6.2 Gói và nhiệm vụ

Gói có DRAFT, ACTIVE, COMPLETED, CANCELLED; archived_at là cờ chỉ đọc riêng. DRAFT → ACTIVE khi Chủ duyệt. ACTIVE tự thành COMPLETED khi có ít nhất một bài không hủy và tất cả bài không hủy đã PUBLISHED. Nếu tất cả bài bị hủy, Chủ phải chọn hủy gói, không hiển thị hoàn thành. Mở lại bài làm gói COMPLETED trở lại ACTIVE. Gói lưu trữ phải khôi phục trước khi thao tác; không lưu trữ khi còn AI run chưa kết thúc.

Ba nhiệm vụ/bài có WAITING, READY, IN_PROGRESS, DONE, CANCELLED. Trạng thái nhiệm vụ được cập nhật bằng cùng giao dịch với trạng thái bài, không có nút tùy ý sửa độc lập. Trả từ EDITING về WRITING mở lại việc viết và đưa biên tập về WAITING. Từ OWNER_REVIEW trả EDITING mở lại biên tập. Duyệt mở READY cho xuất bản; đăng hoàn tất việc xuất bản. Lịch sử các vòng không bị ghi đè.

### 6.3 Đồng thời và phiên bản

Mỗi đối tượng sửa có row_version. Lệnh gửi expected_row_version; lệch trả 409 và yêu cầu tải bản mới, không ghi đè. Nộp bài, duyệt, đổi người và ghi nhận đăng dùng transaction và idempotency key để nhấp hai lần không tạo hai quyết định. Số phiên bản tăng tuần tự duy nhất trong mỗi bài. Approval chỉ hợp lệ khi trỏ phiên bản mới nhất đã qua biên tập; tạo nội dung mới không được giữ hiệu lực duyệt cũ.

## 7. Màn hình và hành vi

| Mã | Màn hình | Thành phần và thao tác |
|---|---|---|
| UI01 | Tổng quan Chủ | Ba vùng: Cần quyết định, Bị chặn/trễ hạn, Tiến độ gói. Bấm thẻ tới đúng đối tượng. Không dùng điểm AI hoặc phần trăm giả |
| UI02 | Thương hiệu | Form mục 4; lưu tăng revision; cảnh báo không tự áp dụng vào gói đã duyệt |
| UI03 | Thành viên và bố trí | Mời/thu hồi; gán điều phối theo gói và ba vị trí theo bài. Hiển thị một người kiêm nhiều vị trí |
| UI04 | Danh sách/chi tiết gói | Lọc trạng thái; kế hoạch dạng bảng; thêm bài; duyệt; lịch sử thay đổi; tiến độ x/y bài đã đăng |
| UI05 | Chi tiết bài | Brief/snapshot, người/hạn, trạng thái, phiên bản đang xem, nội dung, checklist, quyết định, xuất bản, timeline |
| UI06 | Việc của tôi | Chỉ việc được giao; ưu tiên bị chặn, trễ hạn, đến hạn; bộ lọc gói/vị trí; một hành động chính theo bước |
| UI07 | Kết nối AI — R1.1 | Nhà cung cấp/model, nhập key kiểu mật khẩu, test/lưu/gỡ, quyền sử dụng, mức sử dụng; không hiển thị lại key |

Mỗi màn hình có loading, empty, error, forbidden, stale-data và success. Empty state gợi ý thao tác phù hợp quyền. Lưu lỗi giữ nội dung trong form đang mở và cho thử lại. R1 không cam kết lưu khi đóng tab/offline; cảnh báo rời trang nếu chưa lưu. Trên điện thoại dùng danh sách/thẻ thay bảng rộng, nút duyệt và nội dung không bị che.

Tổng quan MEMBER chỉ hiển thị việc và số liệu thuộc phạm vi truy cập; không lộ tên gói/bài khác qua bộ đếm. Lọc và phân trang phía server, mặc định 20 dòng/trang.

## 8. Thông báo và nhắc việc

R1 có hộp thông báo trong ứng dụng; không email, push hoặc Zalo. Tạo thông báo khi được giao/đổi việc, có yêu cầu sửa, có bài chờ duyệt, có blocker hướng tới mình hoặc blocker được giải quyết. Không thông báo cho chính người thao tác. Chuyển trạng thái sinh thông báo một lần theo event_id và recipient_id.

Trễ hạn tính từ trạng thái hiện tại và deadline của bước; hiển thị khi mở trang, chưa có job nhắc định kỳ. Thu hồi quyền làm thông báo cũ không còn mở được nội dung; danh sách thông báo cũng phải lọc quyền hiện tại.

## 9. Mô hình dữ liệu tối thiểu

PK cho các bảng nghiệp vụ mới là UUID; giữ nguyên PK số nguyên của Django User và bảng thanh toán hiện có. Không đổi PK hoặc thay AUTH_USER_MODEL của cơ sở dữ liệu đã migrate chỉ để khớp mô hình khái niệm. Thời gian có timezone. Các bảng thuộc doanh nghiệp đều chứa workspace_id. FK và kiểm tra service phải ngăn liên kết đối tượng giữa hai workspace; dùng unique/composite constraint phù hợp.

| Bảng | Trường chính và ràng buộc |
|---|---|
| users (ánh xạ auth.User hiện có) | Giữ id, username, email, first_name, last_name và mật khẩu/session của Django; không tạo auth_subject hoặc bảng users thứ hai |
| account_email_identities (bổ sung) | user OneToOne, normalized_email unique, verified_at; là nguồn nhận diện email đăng nhập/lời mời, cập nhật qua service đồng bộ và reset xác minh khi đổi email |
| workspaces | id, name, timezone, owner_user_id, created_at |
| memberships | id, workspace_id, user_id, access_role, employment_type, status, ai_use_allowed; unique(workspace_id,user_id) |
| invitations | workspace_id, email, token_hash unique, expires_at, used_at, revoked_at |
| brand_profiles | workspace_id unique, các trường mục 4, revision, updated_by |
| packages | id, workspace_id, coordinator_membership_id, name, objective, channel, start/end, status, plan_revision, brand_snapshot, archived_at, row_version |
| plan_approvals | package_id, plan_revision, immutable_plan_snapshot, owner_id, approved_at |
| content_items | id, workspace_id, package_id, title, brief, CTA, state, blocked_reason/by/at, resolution_note, latest_version_id, approval_id nullable, row_version |
| tasks | item_id, role WRITE/EDIT/PUBLISH, assignee_membership_id, execution_mode, status, due_at; unique(item_id,role) |
| content_versions | item_id, version_no, text, reference_urls, source, author_id, created_at, parent_version_id; immutable, unique(item_id,version_no) |
| review_decisions | item_id, version_id, decision, return_stage, reason, checklist, actor_id, created_at; append-only |
| approvals | item_id, version_id, approved_by, approved_at, invalidated_at/reason; tối đa một approval có hiệu lực/bài |
| publications | item_id, version_id, approval_id, url, published_at, recorded_by, recorded_at; giữ bản ghi cũ khi mở lại |
| feedback | item_id, version_id nullable, author_id, body, created_at; phản hồi tổng thể, không chat |
| audit_events | workspace_id, entity_type/id, actor_id, action, changed_fields, occurred_at; không chứa key hoặc toàn văn prompt |
| notifications | recipient_id, workspace_id, event_id, entity_id, read_at; unique(recipient_id,event_id) |
| ai_connections — R1.1 | workspace_id, provider, encrypted_secret, key_version, status, model_id, tested_at; một kết nối active/workspace |
| ai_runs — R1.1 | workspace_id, item_id, actor_id, connection_id, input_snapshot, base_row_version, status, provider_request_id, usage, output_version_id, error_code, idempotency_key |

Không lưu danh sách API key trong hồ sơ người dùng, nội dung bài hoặc audit. Khóa mã hóa đặt ngoài CSDL. Không xây bảng model tự động cập nhật từ nguồn tùy ý trong R1.1.

## 10. Hợp đồng API nội bộ đề xuất

Đây là hợp đồng nghiệp vụ của SaaS, không phải schema của nhà cung cấp AI. Bảng bên dưới là thiết kế JSON API logic dưới /api/v1; R1 dùng Django views/forms/HTMX và chỉ hiện thực JSON endpoint khi cần, không bắt buộc xây toàn bộ REST API. Hành động form dùng POST, CSRF và service chung; GET trả trang/fragment, validation và conflict phải render được. Các mã HTTP bên dưới áp dụng cho JSON; xem quy tắc HTMX ở mục 17. Mọi transport đều xác thực, kiểm tra workspace và quyền trên mọi request. Không cho client tự đặt actor_id, approval_id hay state tùy ý.

| Nhóm endpoint | Hành vi |
|---|---|
| POST /workspaces; GET /workspaces | Tạo workspace, liệt kê workspace được tham gia |
| GET/PATCH /workspaces/{w}/brand | Đọc/sửa theo quyền; revision bắt buộc khi sửa |
| POST /workspaces/{w}/invitations; POST /invitations/accept | Tạo hoặc nhận lời mời; không gửi email tự động |
| POST /workspaces/{w}/members/{m}/revoke | Thu hồi và chuyển nhiệm vụ nguyên tử |
| POST/GET /workspaces/{w}/packages | Tạo và liệt kê gói đã lọc quyền |
| GET/PATCH /packages/{p}; POST /packages/{p}/approve-plan | Sửa theo trạng thái và duyệt snapshot |
| POST /packages/{p}/items; GET/PATCH /items/{i} | Tạo/sửa bài; kiểm tra kế hoạch, quyền và revision |
| POST /items/{i}/assignments | Chủ/điều phối đổi người; kèm expected revision và lý do |
| POST /items/{i}/versions | Tạo bản mới; không có PATCH nội dung version |
| POST /items/{i}/actions | Enum start, submit_edit, submit_owner, request_changes, withdraw_review, approve, block, unblock, reopen, cancel |
| POST /items/{i}/publications | Ghi nhận xuất bản có URL, thời điểm, approval/version |
| PATCH /publications/{id} | Sửa metadata có lý do và audit; không đổi version |
| GET /workspaces/{w}/dashboard; GET /tasks/mine | Tổng hợp theo quyền hiện tại |
| GET /notifications; POST /notifications/{id}/read | Đọc thông báo theo người nhận |
| POST /workspaces/{w}/ai-connection/test; PUT/DELETE /workspaces/{w}/ai-connection | R1.1; chỉ Chủ |
| POST /items/{i}/ai-runs; GET /ai-runs/{r}; POST /ai-runs/{r}/cancel | R1.1; kiểm tra feature flag và quyền sử dụng |

Mutation có expected_row_version và Idempotency-Key khi tạo quyết định/run/xuất bản. Response lỗi: code, message tiếng Việt, field_errors, request_id; không chứa key hoặc raw provider response. HTTP 401 chưa đăng nhập; 403 không được thao tác; 404 không thấy; 409 xung đột; 422 dữ liệu/quy trình sai; 429 giới hạn; 502/504 lỗi nhà cung cấp hoặc timeout. Thay đổi DB, audit và notification/outbox phải cùng transaction.

## 11. BYOK — Spec R1.1 có giới hạn

### 11.1 Phạm vi và cấu hình

Người dùng cung cấp key riêng; hệ thống vẫn phải tích hợp nhà cung cấp. Một adapter đầu tiên được chọn khi bắt đầu R1.1; không chốt tên model, đơn giá hoặc cam kết tương thích trong tài liệu này. Chỉ bật khi đã kiểm tra tài liệu hiện hành, hợp đồng request/response, quyền BYOK và xử lý dữ liệu của nhà cung cấp.

URL nhà cung cấp được cố định phía server theo allowlist; không có ô URL tùy ý. Model nằm trong danh sách đã kiểm thử. Nếu không có model hợp lệ hoặc cấu hình giới hạn đầu vào/đầu ra thì tính năng không được bật. Test kết nối phải báo trước khả năng phát sinh lượng sử dụng nếu cần request suy luận nhỏ.

Key nhập qua HTTPS, backend mã hóa rồi lưu; chỉ trả trạng thái kết nối. Không dùng localStorage để giữ key, không trả key về UI, không đưa key vào prompt/log/analytics. Gỡ kết nối xóa secret lưu tại SaaS và chặn lần gọi mới; UI giải thích không đồng nghĩa thu hồi key tại nhà cung cấp. Xóa key không hủy chi phí của request đã gửi.

### 11.2 Tác vụ duy nhất: Tạo bản nháp

Chỉ Chủ hoặc người viết/biên tập được phân công, có ai_use_allowed mới được chạy. Chỉ cho chạy khi bài WRITING hoặc EDITING và không bị chặn. Modal hiển thị nhà cung cấp, model, thông tin thương hiệu/brief nào sẽ gửi, giới hạn và thông báo phí API do tài khoản Chủ chịu. Mặc định không gửi tên thành viên, lịch sử phản hồi hoặc tài liệu ngoài chưa được chọn.

Sau xác nhận: lưu run và input snapshot → worker gọi provider → lưu output thành content_version nguồn BYOK. Không tự nộp biên tập, duyệt hay xuất bản. Nội dung do model trả về được coi là văn bản không tin cậy, không thực thi mã hoặc dùng làm lệnh công cụ.

### 11.3 Chạy, giới hạn, lỗi

Run có QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, UNKNOWN. Mặc định một run đang hoạt động/bài, hai run đang hoạt động/workspace, tối đa 20 lần gọi tạo nội dung/workspace/ngày theo UTC. Con số là hạn mức thử nghiệm đề xuất, không phải định giá. Mỗi adapter phải có hard cap token đầu vào/đầu ra phù hợp model và timeout 120 giây; không tự chia thành nhiều request hoặc cắt mất brief âm thầm.

Không retry tự động trong R1.1. Lỗi key: dừng và hướng dẫn Chủ kiểm tra. Hết quota/rate limit: giữ nội dung, cho chạy lại thủ công sau. Timeout sau khi gửi: UNKNOWN, nói rõ có thể đã tính phí; chỉ chạy lại sau xác nhận. Idempotency nội bộ chống nhấp đôi nhưng không hứa provider không tính phí hai lần nếu người dùng chủ động chạy lại.

Nếu người dùng sửa bài, đổi người, chặn bài hoặc thu hồi quyền khi run đang chạy: kết quả không tự thành bản mới nhất. Lưu kết quả ở run để Chủ/người có quyền hiện tại xem và chủ động nhập thành version sau; không mở quyền lại cho người đã bị thu hồi. Worker phải kiểm tra quyền và revision trước ghi. Hủy là best effort; không hứa hủy được xử lý phía provider.

Hiển thị token thực tế nếu provider trả về; không bịa số liệu nếu thiếu. Chi phí tiền chỉ là ước tính khi có bảng giá có ngày cập nhật; hóa đơn nhà cung cấp là nguồn xác nhận. Không tuyên bố hạn mức USD chính xác nếu chưa có cơ chế dự trù và khóa đồng thời. Nhật ký sử dụng và quyền chạy giúp Chủ kiểm soát người sử dụng key của doanh nghiệp.

## 12. Kiến trúc và yêu cầu vận hành

Luồng lõi: trình duyệt + HTMX → Django views/forms → service xác thực/phân quyền → Django ORM → PostgreSQL. R1.1 thêm worker riêng đọc hàng đợi ai_runs trong PostgreSQL → API AI và kho secret. Không để frontend gọi provider bằng key đã lưu. Chưa cần microservices, nhiều agent hoặc bộ máy workflow tổng quát.

Mọi nội dung người dùng/model phải render như văn bản hoặc sanitize theo allowlist. Áp dụng CSRF nếu dùng cookie session, cookie bảo mật, rate limit đăng nhập/lời mời và không log dữ liệu nhạy cảm. TLS khi truyền dữ liệu. Tách môi trường dev/test/prod; không đưa dữ liệu thật hoặc key thật vào fixture.

Mục tiêu thử nghiệm: 20 người dùng đồng thời trên bộ dữ liệu 1.000 bài/workspace; p95 API đọc danh sách dưới 1 giây, ghi nghiệp vụ dưới 2 giây, không tính AI và mạng phía người dùng. Đây là tiêu chí kiểm tra, chưa phải SLA thương mại. Có phân trang và index workspace_id, assignee, state, due_at.

Trước pilot dữ liệu thật: sao lưu CSDL hằng ngày, giữ 7 bản, thực hiện một lần phục hồi thử; mục tiêu RPO 24 giờ/RTO 1 ngày. Chính sách lưu giữ/xóa dữ liệu khi đóng tài khoản, điều khoản dữ liệu gửi AI và giá phải được công bố trước phát hành thương mại. Audit nghiệp vụ giữ trong vòng đời workspace; key không có trong bản xuất dữ liệu. R1 chỉ lưu trữ/khôi phục gói, không có nút xóa vĩnh viễn. Không dùng soft-delete để giả vờ đã đáp ứng yêu cầu xóa dữ liệu.

## 13. Backlog theo thứ tự triển khai

Ước lượng theo độ lớn S/M/L, chưa phải cam kết ngày hoàn thành. Không cần xây song song BYOK để nghiệm thu lõi.

| ID | Hạng mục | Phụ thuộc | Cỡ | Điều kiện hoàn thành |
|---|---|---|---|---|
| B00 | Chuẩn hóa boilerplate, phiên bản, billing flag, email identity và static | — | M | Qua kiểm tra nền mục 19 trước phát triển nghiệp vụ |
| B01 | Workspace, đăng nhập, tenant isolation | B00 | L | Tạo workspace; người A không đọc/sửa dữ liệu workspace B qua API |
| B02 | Thành viên, lời mời, phân quyền | B01 | L | Nhận lời mời đúng email; token hết hạn/tái dùng bị từ chối; thu hồi có hiệu lực |
| B03 | Hồ sơ thương hiệu | B01 | S | Validate; lưu revision; snapshot cũ không bị thay đổi |
| B04 | Gói, kế hoạch, phân công | B02,B03 | L | Chủ duyệt kế hoạch đủ trường; sinh đúng nhiệm vụ, chống nhấp đôi |
| B05 | Phiên bản và luồng viết/biên tập | B04 | L | Sao chép brief; nộp/sửa không ghi đè; checklist và chuyển bước đúng quyền |
| B06 | Chủ duyệt, mở lại, trạng thái | B05 | L | Duyệt gắn đúng version; bản cũ/xung đột bị từ chối; reopen vô hiệu approval |
| B07 | Xuất bản và hoàn thành gói | B06 | M | URL bắt buộc; giữ lịch sử; tính hoàn thành/hủy đúng |
| B08 | Blocker, đổi người, thu hồi | B04–B07 | M | Không mồ côi trách nhiệm; không vượt bước khi bị chặn |
| B09 | Tổng quan, Việc của tôi, thông báo | B04–B08 | M | Đếm đúng theo quyền; link tới tác vụ; không lộ thông tin qua count |
| B10 | Responsive, lỗi, backup, QA lõi | B01–B09 | L | Qua kịch bản mục 14 và phục hồi thử |
| A01 | Adapter và secret BYOK | B10 | L | Kiểm chứng provider/model; key không lộ; test/gỡ đúng quyền |
| A02 | Worker tạo nháp và hạn mức | A01 | L | Một run/bài; timeout/unknown; lưu version không tự chuyển bước |
| A03 | Usage, quyền và QA BYOK | A02 | M | Thu hồi giữa run; kết quả stale; không retry ngầm; thông báo phí rõ |

Thứ tự milestone: M0 chuẩn hóa B00; M1 nền tảng B01–B04; M2 luồng nội dung B05–B08; M3 pilot lõi B09–B10; M4 BYOK A01–A03. Hoàn thành M3 là R1 dùng được; không gọi R1.1 sẵn sàng nếu A01–A03 chưa qua kiểm thử.

## 14. Bộ nghiệm thu có thể chạy

Dữ liệu mẫu: workspace “Trung tâm Anh ngữ mẫu”; một Chủ, một freelancer viết/biên tập, một nhân viên xuất bản; gói 3 bài Facebook. Tạo thêm workspace khác để kiểm tra cách ly.

| ID | Given / When | Then |
|---|---|---|
| AC01 | Không có kết nối AI; hoàn thành gói với AI bên ngoài | Tất cả bước hoạt động, không bị buộc nhập key |
| AC02 | Freelancer biết ID bài của người khác ngoài phạm vi | API trả 404; không lộ title, count hoặc lịch sử |
| AC03 | MEMBER tự gọi endpoint duyệt/kết nối AI | Bị từ chối; dữ liệu không đổi |
| AC04 | Kế hoạch thiếu người hoặc hạn sai thứ tự; Chủ duyệt | 422 có lỗi từng trường; không sinh một phần nhiệm vụ |
| AC05 | Nhấp duyệt kế hoạch hai lần cùng idempotency key | Chỉ một snapshot và một bộ nhiệm vụ |
| AC06 | Nộp v1, biên tập trả sửa, nộp v2 | V1 vẫn nguyên; lý do sửa và người chịu trách nhiệm đúng |
| AC07 | Chủ đang xem v1 trong khi bản hiện hành đã thay đổi | Duyệt thất bại 409; không duyệt nhầm v2 |
| AC08 | Bài đang chờ duyệt, người viết gọi lưu phiên bản mới | Bị từ chối tới khi rút/ trả bước hợp lệ |
| AC09 | Duyệt v2, Chủ mở lại để sửa | Approval v2 hết hiệu lực; không cho đăng dựa trên approval cũ |
| AC10 | Hai người sửa cùng row_version | Một ghi thành công, một nhận 409; không mất nội dung âm thầm |
| AC11 | Thu hồi freelancer còn việc đang mở | Việc chuyển cho người thay/Chủ; quyền cũ hết; lịch sử giữ nguyên |
| AC12 | Bài bị chặn; thử nộp/duyệt/đăng | Bị từ chối; lưu nháp hoặc giải quyết blocker vẫn được theo quyền |
| AC13 | Ghi nhận đăng thiếu URL hoặc chưa duyệt | Bị từ chối; nhập hợp lệ ghi đúng người, giờ và version |
| AC14 | 2 bài đăng, 1 bài hủy; hoặc cả 3 bài hủy | Trường hợp đầu hoàn thành 2/2 và hiện 1 hủy; trường hợp sau không hiện hoàn thành |
| AC15 | Sửa thương hiệu sau duyệt kế hoạch | Snapshot gói không tự đổi; áp dụng lại cần thao tác Chủ và lịch sử |
| AC16 | Màn hình 390 px, Chủ duyệt bài | Đọc và thao tác được, không tràn ngang nội dung chính |
| AC17 | Mất kết nối khi lưu form | Không báo thành công giả; giữ nội dung đang nhập, thử lại không tạo trùng |
| AC18 | Khôi phục bản sao lưu thử | Đọc được gói/phiên bản/quyết định và quyền nhất quán |
| AI01 | Chạy BYOK hợp lệ | Lưu draft nguồn BYOK, không tự duyệt/chuyển bước |
| AI02 | Key sai, hết quota hoặc timeout sau gửi | Lỗi riêng; không retry ngầm; timeout có cảnh báo có thể đã tính phí |
| AI03 | Thu hồi quyền/đổi brief khi AI đang chạy | Không tự áp dụng kết quả cũ; người bị thu hồi không đọc được run |
| AI04 | Inspect response, log, analytics | Không có secret; API không trả key đầy đủ |
| AI05 | Nhấp chạy hai lần hoặc vượt giới hạn | Không tạo request trùng do double-click; vượt hạn mức bị chặn trước gọi |

Release gate R1: AC01–AC18 đạt, không còn lỗi cách ly dữ liệu/quyền, mất nội dung hoặc duyệt sai bản; có hướng dẫn thử một gói. R1.1 thêm AI01–AI05 và hoàn tất kiểm chứng adapter/model. Các điều kiện là tiêu chuẩn cần thực hiện, không phải kết quả đã kiểm thử.

## 15. Đo giá trị trong pilot

Pilot đề xuất: 3–5 Chủ có nhu cầu phối hợp content, mỗi người chạy ít nhất 2 gói thật. Không coi quy mô này đủ để suy rộng thị trường.

| Câu hỏi | Dữ liệu cần lấy | Tín hiệu xem xét tiếp tục |
|---|---|---|
| Khởi tạo có dễ không? | Quan sát lần đầu; thời gian tạo gói đầu tiên | Chủ hoàn thành mà không cần người phát triển làm hộ |
| Giảm điều phối không? | Chủ ghi thời gian điều phối một gói trước/sau | Giảm thời gian với khối lượng tương đương; không chỉ cảm giác dashboard đẹp |
| Có tạo nhập liệu trùng không? | Số lần chép lại thông tin và phỏng vấn người thực hiện | Người dùng nộp kết quả một lần, không phải duy trì thêm bảng song song |
| Chủ có thấy việc cần làm? | Task test tìm bài cần duyệt/việc bị kẹt | Tìm đúng mà không nhắn hỏi |
| Có quay lại không? | package_created, plan_approved, version_submitted, publication_recorded | Có gói thứ hai được vận hành thực tế |
| Có thể thu phí không? | Đề nghị gói thử trả phí sau khi chốt giá | Ghi nhận quyết định thực tế, không đồng nhất lời khen với mua |

Analytics chỉ lưu event, ID và thời gian cần thiết; không thu API key, toàn văn nội dung hoặc prompt. Nếu người thực hiện vẫn cần duy trì Docs/Excel/Zalo rồi nhập lại nhiều lần, ưu tiên sửa thao tác bàn giao trước khi thêm AI.

## 16. Các quyết định còn mở và điểm chặn

| Mục | Mặc định hiện tại | Khi nào cần chốt |
|---|---|---|
| Framework, CSDL, auth | Django + HTMX, PostgreSQL, Django session auth theo mục 17 | Đã chọn hướng; kiểm tra migration/dữ liệu trước B00 |
| Hosting | Tận dụng cấu hình Render của repo; Docker là đường chạy thay thế | Chọn tài khoản/gói triển khai sau; chưa mua hoặc deploy |
| Nhà cung cấp/model BYOK | Chưa chọn; feature flag tắt | Trước A01; không chặn R1 |
| Giá SaaS và phụ phí BYOK | Để Chủ sản phẩm quyết định sau; không dùng giá mẫu boilerplate | Khi Chủ yêu cầu triển khai thương mại |
| Hạn mức thương mại | Các giới hạn hiện tại chỉ cho pilot | Sau dữ liệu pilot, trước công bố gói |
| Chính sách dữ liệu/đóng tài khoản | Cần quy trình cụ thể | Trước dữ liệu thật phải có hướng dẫn xử lý; trước thương mại phải công bố đầy đủ |

Không cần giải quyết các ban khác, đa kênh hay custom endpoint để bắt đầu B01–B10. Các mô tả kỹ thuật trong tài liệu là quyết định thiết kế đề xuất, không khẳng định API bên thứ ba đã tích hợp hoặc giá thị trường đã được kiểm chứng.


## 17. Công nghệ triển khai theo repository

**Nguồn kiểm tra:** [pe-oss/SaaS1_PJ_Boilerplate_VietQR_Webhook](https://github.com/pe-oss/SaaS1_PJ_Boilerplate_VietQR_Webhook), nhánh main, commit `0605844bf496fe5be8ef372f98594306a69d11eb`, kiểm tra ngày 12/10/2026. Đã đọc manifest, settings, auth, model thanh toán, URL, template nền và cấu hình triển khai. Đây là kiểm tra mã nguồn, chưa chạy ứng dụng hoặc kiểm thử bảo mật toàn diện. Không có thay đổi mã nguồn hoặc deploy trong lần cập nhật Spec này.

### 17.1 Stack được chọn

| Lớp | Thực tế trong repo | Quyết định cho sản phẩm |
|---|---|---|
| Python | Docker 3.12; Render pin 3.10.11 | Đồng nhất nhánh 3.12 cho local/CI/Docker/Render; pin bản vá lúc triển khai |
| Backend | requirements.txt pin Django 5.1.2 | Giữ Django, nâng lên bản vá được hỗ trợ thuộc 5.2 LTS; khóa dependency sau kiểm thử |
| Frontend | Django Templates; base.html nạp HTMX 2.0.3; CSS và JS riêng | Giữ Templates + HTMX 2.x và CSS/JS; kiểm thử/pin bản vá; không thêm React, Next.js hoặc pipeline Node cho R1 |
| Dữ liệu | SQLite mặc định; dj-database-url và psycopg2-binary đã có | PostgreSQL cho staging, pilot, production và kiểm thử transaction; SQLite chỉ thử giao diện nhanh/local đơn giản |
| Auth | Django User/session, form đăng ký, backend username hoặc email | Tái dùng; bổ sung email identity/xác minh và quyền workspace; không đổi sang JWT hoặc dịch vụ auth khác |
| Static | WhiteNoise, collectstatic; cấu hình storage cũ | Giữ WhiteNoise; chuyển cấu hình sang STORAGES, kiểm tra file manifest dưới DEBUG=False |
| Server | Gunicorn WSGI | Giữ Gunicorn; request web ngắn, worker AI chạy riêng |
| Triển khai | render.yaml, build.sh và Dockerfile | Tận dụng Render làm cấu hình mặc định, không cam kết gói free; PostgreSQL độc lập, env production rõ ràng |
| Thanh toán | Order, PaymentHistory, VietQR và luồng PayOS/SePay; dịch vụ Telegram | Giữ module để dùng sau, tắt toàn bộ đường thương mại ở MVP |
| AI | Không có dependency/model hoặc worker AI trong cây repo | Không cần ở R1; thêm adapter server-side và worker ở R1.1 |

Không coi việc đã khai báo psycopg2 là production đã dùng PostgreSQL: phải cung cấp DATABASE_URL và kiểm tra kết nối. Không thay CSDL production bằng SQLite để tránh cấu hình ban đầu vì tiêu chí đồng thời/transaction cần kiểm thử trên PostgreSQL.

### 17.2 Cấu trúc module đề xuất

- `apps/accounts`: tái dùng đăng nhập/đăng ký/đổi mật khẩu; bổ sung xác minh email và identity, giới hạn thử đăng nhập.
- `apps/workspaces`: Workspace, Membership, Invitation, BrandProfile; chính sách quyền và membership context.
- `apps/content`: gói, kế hoạch, bài, nhiệm vụ, phiên bản, quyết định, xuất bản; forms, views, services và selectors.
- `apps/activity`: audit/outbox, thông báo, bộ đếm đã lọc quyền.
- `apps/ai`: chỉ R1.1; connection, adapter, run, worker management command và usage.
- `apps/payments`: giữ migrations/bảng hiện tại; route và chức năng tắt bằng cấu hình; không dùng trạng thái thanh toán để xác định quyền content.
- `templates/content`, `templates/workspaces`, `templates/partials`: kế thừa base.html và mở rộng static/css/app.css, static/js/app.js.

Tên module trên là cấu trúc sẽ thêm, không phải thành phần đã tồn tại. Chưa cần DRF, Redis, Celery, FastAPI hoặc một backend khác. Nghiệp vụ ở service function dùng chung cho form và JSON để không nhân đôi quy tắc.

### 17.3 HTMX và giao diện server-rendered

Dùng form POST có CSRF; validate với Django Forms; POST thành công dùng redirect hoặc trả fragment phù hợp. Endpoint HTML và JSON phải có hợp đồng response riêng, không trả JSON vào vùng HTML. Template/fragment không chứa key, dữ liệu workspace khác hoặc HTML AI chưa xử lý.

Lỗi form có thể trả fragment 200 với trạng thái validation rõ ràng, không phát success event. Với 409/403/422 nếu dùng status này trên HTMX, cấu hình xử lý response trong app.js và kiểm thử hiển thị lỗi, giữ nội dung nhập; không giả định HTMX sẽ tự swap các response lỗi. Form không dùng JavaScript vẫn có trang lỗi/redirect đọc được.

Token idempotency/expected_row_version nằm trong hidden field hoặc header; kiểm tra tại server. Không dùng HTTP PATCH trực tiếp từ form chuẩn: route POST gọi cùng service tương ứng thao tác PATCH của hợp đồng logic mục 10.

### 17.4 Auth cần bổ sung, không có sẵn trong template

Repo dùng User mặc định và kiểm tra trùng email ở form; điều đó chưa phải ràng buộc unique ở CSDL. Backend đang chọn tài khoản đầu tiên khi có nhiều kết quả. Cần sửa để trường hợp email/username mơ hồ bị từ chối, không chọn tùy ý.

Giữ User hiện có, bổ sung AccountEmailIdentity OneToOne với normalized_email unique và verified_at. Backfill từ User.email: nếu trùng/không hợp lệ, dừng migration dữ liệu và lập danh sách xử lý, không tự gộp/xóa tài khoản. Mọi đăng ký/đổi email/admin flow phải cập nhật qua service; kiểm tra unique ở DB trong transaction, không chỉ ở form. Đăng nhập email đọc identity; đăng nhập username đọc User; nếu định danh khớp hai người thì trả lỗi chung.

Lời mời yêu cầu identity đã verified. Thêm link xác minh qua email tài khoản có token hết hạn/một lần, rate limit và reset verified khi đổi email. Repo chỉ dùng console email backend: cần cấu hình SMTP hoặc dịch vụ gửi email giao dịch trước pilot. Đây là email hạ tầng xác thực, không phải email báo tiến độ hoặc gửi lời mời tự động. Không đánh dấu verified chỉ vì người dùng tự nhập đúng chuỗi email. Các tài khoản cũ chưa xác minh vẫn cần hoàn thành bước này trước nhận lời mời.

Chủ workspace không được gán is_staff/is_superuser. Django admin chỉ dành cho quản trị vận hành; màn hình Chủ phải dùng quyền workspace riêng.

### 17.5 Dữ liệu, transaction và worker

Dùng Django ORM + migrations. Các foreign key tới người dùng dùng settings.AUTH_USER_MODEL. UUID chỉ cho bảng mới; không áp dụng UUID ngược vào User/Order/PaymentHistory. Bảng nghiệp vụ dùng PROTECT cho tham chiếu cần giữ lịch sử hoặc cơ chế vô hiệu tài khoản rõ ràng; không để xóa User cascade làm mất quyết định/phiên bản.

Service chuyển bước dùng transaction.atomic, kiểm tra row_version và khóa đối tượng cần thiết trên PostgreSQL. DB constraints cho version_no, idempotency, membership và approval có hiệu lực; mọi truy vấn lọc workspace và phạm vi phân công trước khi lấy đối tượng. Unit test SQLite không thay thế test transaction PostgreSQL.

R1.1 khởi đầu dùng bảng ai_runs làm hàng đợi bền vững và management command chạy worker riêng. Worker claim run bằng transaction/row lock, có lease/heartbeat và dấu đã gửi provider. Restart chỉ tự nhận lại run chưa gửi; run có khả năng đã gửi chuyển UNKNOWN, không gọi lại tự động. Quota/counter được khóa nguyên tử để hai worker không vượt giới hạn. Không giữ DB transaction mở suốt cuộc gọi HTTP. Đây là phần phải xây mới; không tuyên bố boilerplate đã có queue.

Khóa mã hóa BYOK lấy từ secret môi trường riêng, không dùng SECRET_KEY của Django làm khóa mã hóa dữ liệu. Pin thư viện mã hóa được duy trì khi làm A01; version hóa key để có quy trình rotate. Không lưu key trong dotenv được commit hoặc gửi trình duyệt.

## 18. Điều chỉnh template trước phát triển nghiệp vụ

| Phát hiện có bằng chứng | Thay đổi cần làm | Nghiệm thu |
|---|---|---|
| Django 5.1.2 trong requirements.txt | Nâng 5.2 LTS bản vá được hỗ trợ, rà tương thích dependency và pin | migrate/check/test chạy trên Python 3.12 + PostgreSQL |
| Python 3.10.11 ở render.yaml, Docker 3.12 | Đồng nhất phiên bản runtime | Local/CI/deploy khai báo cùng nhánh Python |
| STATICFILES_STORAGE trong settings | Dùng STORAGES với alias staticfiles/default rõ ràng | collectstatic và truy cập CSS/JS dưới DEBUG=False thành công |
| SECRET_KEY có fallback và DEBUG mặc định True | Production fail-fast nếu thiếu SECRET_KEY/DATABASE_URL; DEBUG=False, cookie secure, hosts/origins cụ thể | check --deploy và smoke test production config |
| load_dotenv override=True | Chỉ load local hoặc không ghi đè biến do host cấp | Biến môi trường production không bị file local thay thế |
| Email backend chỉ console, chưa xác minh | Thêm email identity/verification và cấu hình email tài khoản | Không nhận lời mời bằng email tự khai chưa xác minh |
| Dashboard hiện hiển thị thanh toán Free/Pro | Thay bằng dashboard content theo workspace | Quyền dùng content không dựa trên PaymentHistory |
| Nav pricing và route payments luôn được mount | Thêm BILLING_ENABLED=False; ẩn CTA và chặn route tạo order/checkout/webhook/pricing ở cấu hình này | Không có giao dịch phát sinh và không lộ giá mẫu trong R1 |
| build.sh chạy migrate trong build; Docker CMD không migrate | Tách bước migration một lần khi release, hoặc thủ tục triển khai tương đương có kiểm soát | Không migrate đồng thời từ nhiều web worker; có backup và rollback plan |

Module payments có thể giữ trong INSTALLED_APPS để bảo toàn migrations/admin vận hành nhưng route công khai không mở khi billing tắt. Không xóa lịch sử thanh toán hiện có. Giá mẫu PRO_PLAN_PRICE không là quyết định giá của dự án này. Các webhook/Telegram cũng không được tự kích hoạt khi chạy pilot content.

Phạm vi này là danh sách cần thực hiện trong B00, không phải thông báo các lỗi đã được sửa. Chưa có kiểm thử runtime trong lần rà soát này.

## 19. Gate B00 và các quyết định còn lại

B00 hoàn thành khi: dependency/runtime thống nhất; PostgreSQL và migration chạy được; auth hiện có vẫn đăng ký/đăng nhập/đổi mật khẩu; email identity không trùng và xác minh hoạt động; production static đúng; không secret mặc định trong production; billing tắt cả giao diện lẫn backend; CI tối thiểu chạy Django checks và test nghiệp vụ trên PostgreSQL. Các điều kiện quyền/workspace vẫn được xây và nghiệm thu ở B01–B02, không coi chúng có sẵn từ Django login_required.

**Giá bán:** Chủ sản phẩm quyết định sau; không thêm mức giá, gói trả phí hoặc phụ phí BYOK vào Spec lúc này. **AI:** nhà cung cấp/model chưa chọn, không chặn R1. **Hosting:** tận dụng cấu hình Render nhưng chưa chọn/mua gói, chưa deploy. **Mã nguồn:** lần này chỉ điều chỉnh Spec theo repo; việc triển khai B00 trở đi là công việc tiếp theo.

Nguồn kỹ thuật đối chiếu:

- [Manifest của repo](https://github.com/pe-oss/SaaS1_PJ_Boilerplate_VietQR_Webhook/blob/0605844bf496fe5be8ef372f98594306a69d11eb/requirements.txt).
- [Settings](https://github.com/pe-oss/SaaS1_PJ_Boilerplate_VietQR_Webhook/blob/0605844bf496fe5be8ef372f98594306a69d11eb/core/settings.py), [template nền](https://github.com/pe-oss/SaaS1_PJ_Boilerplate_VietQR_Webhook/blob/0605844bf496fe5be8ef372f98594306a69d11eb/templates/base.html).
- [Django support table](https://www.djangoproject.com/download/): 5.1 hết hỗ trợ mở rộng 03/12/2025; 5.2 LTS hỗ trợ mở rộng đến 04/2028. Chọn bản vá hiện hành khi khóa dependency.
- [Django 5.1 release notes](https://docs.djangoproject.com/en/5.1/releases/5.1/): STATICFILES_STORAGE đã bị loại bỏ; [STORAGES](https://docs.djangoproject.com/en/5.2/ref/settings/#storages) là cấu hình thay thế.
