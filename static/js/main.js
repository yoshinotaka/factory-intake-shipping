// 新・出荷システム - メインスクリプト

document.addEventListener('DOMContentLoaded', function() {
    // フラッシュメッセージの自動非表示（5秒後）
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});
