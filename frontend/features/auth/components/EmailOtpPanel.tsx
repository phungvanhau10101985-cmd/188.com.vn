'use client';

import { useEffect, useState } from 'react';
import { Alert, Button, Checkbox, Form, Input, Typography } from 'antd';
import { authAPI } from '../api/auth-api';
import { useAuth } from '../hooks/useAuth';
import { canPersistTrustedDevice, getOrCreateDeviceId } from '@/lib/auth-device-id';
import { getLoginRedirectFromUrl } from '@/lib/auth-redirect';

export default function EmailOtpPanel() {
  const { setSessionFromEmailAuth, setSessionFromToken } = useAuth();
  const [emailForm] = Form.useForm();
  const [otpForm] = Form.useForm();
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [emailVal, setEmailVal] = useState('');
  const [rememberDevice, setRememberDevice] = useState(true);
  const [canTrustDevice, setCanTrustDevice] = useState(true);

  useEffect(() => {
    const ok = canPersistTrustedDevice();
    setCanTrustDevice(ok);
    if (!ok) setRememberDevice(false);
  }, []);

  const onSend = async (values: { email: string }) => {
    setError('');
    setInfo('');
    setLoading(true);
    const browserId = getOrCreateDeviceId();
    if (!browserId || browserId.length < 8) {
      setError('Không tạo được mã thiết bị. Bật cookie/lưu trữ trình duyệt.');
      setLoading(false);
      return;
    }
    try {
      const nextPath = getLoginRedirectFromUrl();
      const r = await authAPI.emailAuthRequest({
        email: values.email.trim(),
        next: nextPath,
        remember_device: canTrustDevice && rememberDevice,
        browser_id: browserId,
      });
      setEmailVal(values.email.trim());
      if (r.auto_signed_in && r.user) {
        if (r.access_token) {
          setSessionFromToken(
            {
              access_token: r.access_token,
              token_type: r.token_type || 'bearer',
              user: r.user,
            },
            r.next
          );
        } else {
          setSessionFromEmailAuth(r.user, r.next);
        }
        return;
      }
      setInfo(r.message || 'Đã gửi mã.');
      setStep('code');
      otpForm.resetFields();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Không thực hiện được. Thử lại.');
    } finally {
      setLoading(false);
    }
  };

  const onVerify = async (values: { otp: string }) => {
    setError('');
    setLoading(true);
    try {
      const r = await authAPI.emailAuthVerifyOtp({
        email: emailVal,
        otp: values.otp,
        remember_device: canTrustDevice && rememberDevice,
        browser_id: getOrCreateDeviceId(),
        next: getLoginRedirectFromUrl(),
      });
      if (r.user) {
        if (r.access_token) {
          setSessionFromToken(
            {
              access_token: r.access_token,
              token_type: r.token_type || 'bearer',
              user: r.user,
            },
            r.next
          );
        } else {
          setSessionFromEmailAuth(r.user, r.next);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Đăng nhập thất bại');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-gray-200 space-y-3">
      <p className="text-sm text-center text-gray-600 mb-0">Hoặc nhập email để nhận mã</p>
      {canTrustDevice ? (
        <Typography.Paragraph type="secondary" className="!mb-0 text-xs text-center leading-relaxed">
          Email đã từng xác thực OTP trên hệ thống có thể <strong>vào luôn</strong> khi bấm Gửi mã (kể cả ẩn danh).
          Tuỳ chọn tin cậy thiết bị chỉ bổ sung cho <strong>trình duyệt này</strong>; ẩn danh là phiên riêng với
          cửa sổ thường.
        </Typography.Paragraph>
      ) : (
        <Alert
          type="info"
          showIcon
          className="text-sm"
          message="Chế độ ẩn danh hoặc chặn lưu trữ"
          description="Không ghi nhớ thiết bị giữa các phiên. Mỗi lần mở phiên ẩn danh mới hoặc khi trình duyệt xóa dữ liệu, bạn sẽ cần mã OTP lại — đây là hành vi bình thường để bảo mật."
        />
      )}

      {error ? (
        <Alert type="error" message={error} showIcon className="text-sm" />
      ) : null}
      {info && step === 'code' ? (
        <Alert type="success" message={info} showIcon className="text-sm" />
      ) : null}

      {step === 'email' ? (
        <Form form={emailForm} layout="vertical" onFinish={onSend} className="!mt-2">
          <Form.Item
            name="email"
            label="Email"
            rules={[{ required: true, type: 'email', message: 'Nhập email hợp lệ' }]}
          >
            <Input type="email" autoComplete="email" placeholder="email@example.com" size="large" />
          </Form.Item>
          {canTrustDevice ? (
            <Form.Item className="!mb-2">
              <Checkbox checked={rememberDevice} onChange={(e) => setRememberDevice(e.target.checked)}>
                Tin cậy thiết bị này (30 ngày) sau khi đăng nhập
              </Checkbox>
            </Form.Item>
          ) : null}
          <Button type="default" htmlType="submit" block size="large" loading={loading}>
            Gửi mã
          </Button>
        </Form>
      ) : (
        <Form form={otpForm} layout="vertical" onFinish={onVerify} className="!mt-2">
          <Typography.Text type="secondary" className="text-xs block mb-2">
            Đang gửi tới: {emailVal}
          </Typography.Text>
          <Form.Item
            name="otp"
            label="Mã OTP"
            rules={[{ required: true, min: 4, message: 'Nhập mã trong email' }]}
          >
            <Input
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6 số"
              size="large"
              className="tracking-widest"
              maxLength={8}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, '').slice(0, 8);
                otpForm.setFieldValue('otp', v);
              }}
            />
          </Form.Item>
          <div className="flex gap-2">
            <Button
              type="default"
              className="flex-1"
              onClick={() => {
                setStep('email');
                setInfo('');
                setError('');
                otpForm.resetFields();
              }}
            >
              Đổi email
            </Button>
            <Button type="primary" htmlType="submit" className="flex-1" loading={loading}>
              Xác nhận
            </Button>
          </div>
        </Form>
      )}
    </div>
  );
}
