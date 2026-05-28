/**
 * 建议反馈表单组件
 * 模态框 + 表单提交，带幂等性和防重复
 */
export default () => ({
  showModal: false,
  content: '',
  contact: '',
  honeypot: '',
  isSubmitting: false,
  submitted: false,
  error: '',
  idempotencyKey: '',

  open() {
    this.showModal = true;
    this.submitted = false;
    this.error = '';
    this.content = '';
    this.contact = '';
    this.honeypot = '';
    this.idempotencyKey = this.generateKey();
    document.body.style.overflow = 'hidden';
    this.$nextTick(() => {
      const textarea = this.$refs.contentInput;
      if (textarea) textarea.focus();
    });
  },

  close() {
    this.showModal = false;
    document.body.style.overflow = '';
  },

  generateKey() {
    return crypto.randomUUID
      ? crypto.randomUUID()
      : Date.now().toString(36) + Math.random().toString(36).slice(2);
  },

  getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      cookie = cookie.trim();
      if (cookie.startsWith(name + '=')) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return '';
  },

  validate() {
    if (!this.content.trim()) {
      this.error = '请输入反馈内容';
      return false;
    }
    if (this.content.trim().length < 10) {
      this.error = '反馈内容至少需要10个字符';
      return false;
    }
    if (this.content.length > 2000) {
      this.error = '反馈内容不能超过2000个字符';
      return false;
    }
    if (this.contact.length > 200) {
      this.error = '联系方式不能超过200个字符';
      return false;
    }
    return true;
  },

  async submit() {
    this.error = '';
    if (!this.validate()) return;

    this.isSubmitting = true;
    try {
      const formData = new FormData();
      formData.append('content', this.content.trim());
      formData.append('contact', this.contact.trim());
      formData.append('website', this.honeypot);
      formData.append('idempotency_key', this.idempotencyKey);

      const response = await fetch('/_internal/feedback/submit/', {
        method: 'POST',
        headers: { 'X-CSRFToken': this.getCsrfToken() },
        body: formData,
      });

      const data = await response.json();
      if (response.ok && data.success) {
        this.submitted = true;
      } else {
        this.error = data.error || '提交失败，请稍后再试';
      }
    } catch (e) {
      this.error = '网络错误，请稍后再试';
    } finally {
      this.isSubmitting = false;
    }
  },
});
