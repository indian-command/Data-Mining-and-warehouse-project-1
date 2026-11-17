
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import DiscussionPost, Comment, PostVote


User = get_user_model()


class DiscussionViewsTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        # Create first student
        cls.student_a = User.objects.create_user(
            username="student_a",
            email="student_a@example.com",
            password="TestPass123!"
        )

        # Create second student
        cls.student_b = User.objects.create_user(
            username="student_b",
            email="student_b@example.com",
            password="TestPass123!"
        )

        # Create staff account
        cls.staff = User.objects.create_user(
            username="staff_member",
            email="staff@example.com",
            password="TestPass123!",
            is_staff=True
        )

        # Create a research post
        cls.post = DiscussionPost.objects.create(
            author=cls.student_a,
            title="Applications of AI in Healthcare",
            content="Research about AI and medical image classification."
        )

    # =====================================
    # TEST 1: VIEW DISCUSSION FEED
    # =====================================

    def test_authenticated_member_can_view_feed(self):

        self.client.force_login(self.student_a)

        response = self.client.get(
            reverse("discussions:post_list")
        )

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "discussions/post_list.html"
        )

    # =====================================
    # TEST 2: CREATE POST
    # =====================================

    def test_member_can_create_post(self):

        self.client.force_login(self.student_a)

        response = self.client.post(
            reverse("discussions:post_create"),
            {
                "title": "Machine Learning Research",
                "content": "Exploring machine learning applications."
            }
        )

        self.assertEqual(response.status_code, 302)

        post = DiscussionPost.objects.get(
            title="Machine Learning Research"
        )

        self.assertEqual(post.author, self.student_a)

    # =====================================
    # TEST 3: OWNER CAN EDIT POST
    # =====================================

    def test_author_can_edit_own_post(self):

        self.client.force_login(self.student_a)

        response = self.client.post(
            reverse(
                "discussions:post_edit",
                args=[self.post.id]
            ),
            {
                "title": "Updated Healthcare Research",
                "content": "Updated research content."
            }
        )

        self.assertEqual(response.status_code, 302)

        self.post.refresh_from_db()

        self.assertEqual(
            self.post.title,
            "Updated Healthcare Research"
        )

    # =====================================
    # TEST 4: OTHER MEMBER CANNOT EDIT
    # =====================================

    def test_other_member_cannot_edit_post(self):

        self.client.force_login(self.student_b)

        original_title = self.post.title

        response = self.client.post(
            reverse(
                "discussions:post_edit",
                args=[self.post.id]
            ),
            {
                "title": "Unauthorized Edit",
                "content": "This should not be saved."
            }
        )

        self.assertEqual(response.status_code, 302)

        self.post.refresh_from_db()

        self.assertEqual(
            self.post.title,
            original_title
        )

    # =====================================
    # TEST 5: OWNER CAN DELETE POST
    # =====================================

    def test_author_can_delete_own_post(self):

        self.client.force_login(self.student_a)

        post_id = self.post.id

        response = self.client.post(
            reverse(
                "discussions:post_delete",
                args=[post_id]
            )
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            DiscussionPost.objects.filter(
                id=post_id
            ).exists()
        )

    # =====================================
    # TEST 6: OTHER MEMBER CANNOT DELETE
    # =====================================

    def test_other_member_cannot_delete_post(self):

        self.client.force_login(self.student_b)

        post_id = self.post.id

        response = self.client.post(
            reverse(
                "discussions:post_delete",
                args=[post_id]
            )
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            DiscussionPost.objects.filter(
                id=post_id
            ).exists()
        )

    # =====================================
    # TEST 7: CREATE COMMENT
    # =====================================

    def test_member_can_comment_on_post(self):

        self.client.force_login(self.student_b)

        response = self.client.post(
            reverse(
                "discussions:comment_create",
                args=[self.post.id]
            ),
            {
                "content": "This is a useful research topic.",
                "parent_id": ""
            }
        )

        self.assertEqual(response.status_code, 302)

        comment = Comment.objects.get(
            post=self.post,
            author=self.student_b
        )

        self.assertIsNone(comment.parent)

    # =====================================
    # TEST 8: CREATE REPLY
    # =====================================

    def test_member_can_reply_to_comment(self):

        parent_comment = Comment.objects.create(
            post=self.post,
            author=self.student_a,
            content="Interesting research topic."
        )

        self.client.force_login(self.student_b)

        response = self.client.post(
            reverse(
                "discussions:comment_create",
                args=[self.post.id]
            ),
            {
                "content": "I agree with this research.",
                "parent_id": parent_comment.id
            }
        )

        self.assertEqual(response.status_code, 302)

        reply = Comment.objects.get(
            post=self.post,
            author=self.student_b
        )

        self.assertEqual(
            reply.parent,
            parent_comment
        )

    # =====================================
    # TEST 9: UPVOTE AND REMOVE UPVOTE
    # =====================================

    def test_member_can_toggle_upvote(self):

        self.client.force_login(self.student_b)

        vote_url = reverse(
            "discussions:toggle_upvote",
            args=[self.post.id]
        )

        # First click: Add upvote
        self.client.post(vote_url)

        self.assertTrue(
            PostVote.objects.filter(
                post=self.post,
                user=self.student_b
            ).exists()
        )

        # Second click: Remove upvote
        self.client.post(vote_url)

        self.assertFalse(
            PostVote.objects.filter(
                post=self.post,
                user=self.student_b
            ).exists()
        )

    # =====================================
    # TEST 10: TWO MEMBERS CAN UPVOTE
    # =====================================

    def test_two_members_can_upvote_same_post(self):

        vote_url = reverse(
            "discussions:toggle_upvote",
            args=[self.post.id]
        )

        # Student A votes
        self.client.force_login(self.student_a)
        self.client.post(vote_url)

        # Student B votes
        self.client.force_login(self.student_b)
        self.client.post(vote_url)

        self.assertEqual(
            PostVote.objects.filter(
                post=self.post
            ).count(),
            2
        )

    # =====================================
    # TEST 11: ANONYMOUS ACCESS RESTRICTIONS
    # =====================================

    def test_anonymous_users_cannot_access_discussions(self):

        protected_get_urls = [
            reverse("discussions:post_list"),
            reverse("discussions:post_create"),
            reverse(
                "discussions:post_edit",
                args=[self.post.id]
            ),
        ]

        for url in protected_get_urls:

            response = self.client.get(url)

            self.assertEqual(
                response.status_code,
                302,
                msg=f"Anonymous GET was not redirected: {url}"
            )

        protected_post_urls = [
            reverse(
                "discussions:post_delete",
                args=[self.post.id]
            ),
            reverse(
                "discussions:comment_create",
                args=[self.post.id]
            ),
            reverse(
                "discussions:toggle_upvote",
                args=[self.post.id]
            ),
        ]

        for url in protected_post_urls:

            response = self.client.post(url)

            self.assertEqual(
                response.status_code,
                302,
                msg=f"Anonymous POST was not redirected: {url}"
            )

    # =====================================
    # TEST 12: STAFF CAN MODERATE POSTS
    # =====================================

    def test_staff_can_edit_another_members_post(self):

        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "discussions:post_edit",
                args=[self.post.id]
            ),
            {
                "title": "Moderated Research Post",
                "content": "Updated by authorized staff."
            }
        )

        self.assertEqual(response.status_code, 302)

        self.post.refresh_from_db()

        self.assertEqual(
            self.post.title,
            "Moderated Research Post"
        )
