from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, Profile, School

User = get_user_model()


class AdminUserDirectoryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="School of Computing", code="SC")
        self.dept = Department.objects.create(
            name="Computer Science & AI", code="CSAI", school=self.school
        )
        self.admin_user = User.objects.create_user(
            username="admin_gov",
            email="admin_gov@chanakya.edu.in",
            password="Pass123!",
            first_name="Admin",
            last_name="Gov",
            is_staff=True,
        )
        Profile.objects.create(user=self.admin_user, role="admin", department=self.dept)

        self.student_user = User.objects.create_user(
            username="scholar_student",
            email="student@chanakya.edu.in",
            password="Pass123!",
            first_name="Aarav",
            last_name="Sharma",
        )
        Profile.objects.create(user=self.student_user, role="student", department=self.dept)

    def test_access_control_protection(self):
        # Anonymous redirected to login
        resp = self.client.get(reverse("accounts:admin_users"))
        self.assertEqual(resp.status_code, 302)

        # Authenticated non-admin receives 403 Forbidden
        self.client.force_login(self.student_user)
        resp_get = self.client.get(reverse("accounts:admin_users"))
        self.assertEqual(resp_get.status_code, 403)

        resp_post = self.client.post(
            reverse("accounts:admin_update_role", args=[self.student_user.id]),
            {"role": "faculty"},
        )
        self.assertEqual(resp_post.status_code, 403)

        # Admin receives HTTP 200
        self.client.force_login(self.admin_user)
        resp_admin = self.client.get(reverse("accounts:admin_users"))
        self.assertEqual(resp_admin.status_code, 200)
        self.assertContains(resp_admin, "User Directory &amp; Access Control Console")

    def test_admin_role_update_and_status_toggle(self):
        self.client.force_login(self.admin_user)

        # Role update: student -> faculty
        resp = self.client.post(
            reverse("accounts:admin_update_role", args=[self.student_user.id]),
            {"role": "faculty"},
        )
        self.assertEqual(resp.status_code, 302)
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.role, "faculty")

        # Suspend target user
        resp_susp = self.client.post(
            reverse("accounts:admin_toggle_status", args=[self.student_user.id])
        )
        self.assertEqual(resp_susp.status_code, 302)
        self.student_user.refresh_from_db()
        self.assertFalse(self.student_user.is_active)

        # Reactivate target user
        self.client.post(
            reverse("accounts:admin_toggle_status", args=[self.student_user.id])
        )
        self.student_user.refresh_from_db()
        self.assertTrue(self.student_user.is_active)

        # Self-suspension blocked
        self.client.post(
            reverse("accounts:admin_toggle_status", args=[self.admin_user.id])
        )
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_admin_verify_reset_password_and_delete(self):
        self.client.force_login(self.admin_user)

        # Toggle verification
        self.client.post(
            reverse("accounts:admin_toggle_verify", args=[self.student_user.id])
        )
        self.student_user.profile.refresh_from_db()
        self.assertFalse(self.student_user.profile.is_verified)

        # Reset temporary password
        self.client.post(
            reverse("accounts:admin_reset_password", args=[self.student_user.id]),
            {"temp_password": "TempPass#99"},
        )
        self.student_user.refresh_from_db()
        self.assertTrue(self.student_user.check_password("TempPass#99"))

        # Self-deletion blocked
        self.client.post(
            reverse("accounts:admin_delete_user", args=[self.admin_user.id])
        )
        self.assertTrue(User.objects.filter(pk=self.admin_user.id).exists())

        # Delete target user cleanly
        self.client.post(
            reverse("accounts:admin_delete_user", args=[self.student_user.id])
        )
        self.assertFalse(User.objects.filter(pk=self.student_user.id).exists())
