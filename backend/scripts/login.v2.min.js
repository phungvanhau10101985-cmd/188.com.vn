$(function() {
    $("#FormLogin").submit(function(t) {
        var n = $(this);
        var recaptcha = $('#g-recaptcha-response').val();
        t.preventDefault(), $.ajax({
            url: "/login",
            type: "POST",
            dataType: "json",
            data: n.serialize() + '&token=' + recaptcha
        }).done(function(t) {
            "success" == t.code ? (swal({
                title: "Tuyệt vời!",
                type: "success",
                text: "Bạn đã truy cập thành công.",
                timer: 2e3,
                showConfirmButton: !1
            }), window.location.href = t.comeback.length > 0 ? t.comeback : "/") : swal({
                title: "Không ổn rồi!",
                type: "warning",
                text: t.message,
                timer: 2e3,
                html: !0,
                showConfirmButton: !1
            })
        }).fail(function(t) {
            swal({
                title: 422 == t.status ? "Không ổn rồi!" : "Thật tệ!",
                type: "warning",
                text: 422 == t.status ? t.responseJSON.message : "Có vẻ như server đang quá tải.",
                timer: 2e3,
                html: !0,
                showConfirmButton: !1
            })
        })
    }), $("#global-search").submit(function(t) {
        t.preventDefault();
        window.open("/orders/detail/" + $("#login_search").val(), "_blank").focus();
    }) , $("#btnConfirmation").click(function(t) {
        var n = $("#account").val();
        var recaptcha = $('#g-recaptcha-response').val();
        isEmpty(n) ? swal({
            title: "Không ổn rồi!",
            type: "warning",
            text: "Bạn cần nhập email nhận xác thực",
            timer: 2e3,
            html: !0,
            showConfirmButton: !1
        }) : (t.preventDefault(), $.ajax({
            url: "/rc/send-confirmation-code?account=" + n + "&token=" + recaptcha,
            type: "GET"
        }).done(function(t) {
            "success" == t.code ? swal({
                title: "Tuyệt vời!",
                type: "success",
                text: t.message,
                icon: "success",
                buttons: !0,
                button: "Đóng"
            }, function(t) {
                window.location.href = "/login?email=" + n
            }) : swal({
                title: "Không ổn rồi!",
                type: "warning",
                text: t.message,
                icon: "warning",
                button: "Đóng"
            })
        }).fail(function(t) {
            swal({
                title: 422 == t.status ? "Không ổn rồi!" : "Thật tệ!",
                type: "warning",
                text: 422 == t.status ? t.responseJSON.message : "Có vẻ như server đang quá tải.",
                timer: 2e3,
                html: !0,
                showConfirmButton: !1
            })
        }))
    }), $("#usewithoutaccount").click(function(t) {
        t.preventDefault(), $.ajax({
            url: "/rc/login/1",
            type: "POST",
            dataType: "json",
            data: $("#FormRetailCustomerLogin").serialize()
        }).done(function(t) {
            "success" == t.code ? window.location.href = t.comeback.length > 0 ? t.comeback : "/" : swal({
                title: "Không ổn rồi!",
                type: "warning",
                text: t.message,
                timer: 2e3,
                html: !0,
                showConfirmButton: !1
            })
        }).fail(function(t) {
            swal({
                title: 422 == t.status ? "Không ổn rồi!" : "Thật tệ!",
                type: "warning",
                text: 422 == t.status ? t.responseJSON.message : "Có vẻ như server đang quá tải.",
                timer: 2e3,
                html: !0,
                showConfirmButton: !1
            })
        })
    })
});