
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from research_library.models import ResearchResource

from .models import DiscussionPost, Comment, PostVote
from accounts.models import (
    MemberFollow,
    Profile,
    Topic,
    TopicFollow,
)

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


    # =====================================
    # TEST 13: FOLLOWING FEED
    # =====================================

    def test_following_feed_shows_followed_members_posts(self):

        MemberFollow.objects.create(
            follower=self.student_b,
            followed=self.student_a
        )

        self.client.force_login(self.student_b)

        response = self.client.get(
            reverse("discussions:post_list"),
            {"feed": "following"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.title)
        self.assertEqual(response.context["feed_type"], "following")

    # =====================================
    # TEST 14: FOLLOWED TOPICS FEED
    # =====================================

    def test_topics_feed_shows_posts_with_followed_topics(self):

        topic_one = Topic.objects.create(
            name="Robotics"
        )

        topic_two = Topic.objects.create(
            name="Energy Systems"
        )

        self.post.tags.add(topic_one, topic_two)

        TopicFollow.objects.create(
            user=self.student_b,
            topic=topic_one
        )

        TopicFollow.objects.create(
            user=self.student_b,
            topic=topic_two
        )

        self.client.force_login(self.student_b)

        response = self.client.get(
            reverse("discussions:post_list"),
            {"feed": "topics"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.title)
        self.assertEqual(response.context["feed_type"], "topics")

        # A post matching two followed topics should appear only once
        self.assertEqual(
            response.context["posts"].filter(
                id=self.post.id
            ).count(),
            1
        )

    # =====================================
    # TEST 15: RECOMMENDATIONS BASED ON INTERESTS
    # =====================================

    def test_recommended_feed_uses_profile_topics(self):

        topic = Topic.objects.create(
            name="Machine Learning"
        )

        profile, created = Profile.objects.get_or_create(
            user=self.student_b
        )

        profile.topics.add(topic)

        recommended_post = DiscussionPost.objects.create(
            author=self.student_a,
            title="Machine Learning Applications",
            content="Research about machine learning."
        )

        recommended_post.tags.add(topic)

        unrelated_post = DiscussionPost.objects.create(
            author=self.staff,
            title="Unrelated Research",
            content="A different research subject."
        )

        self.client.force_login(self.student_b)

        response = self.client.get(
            reverse("discussions:post_list"),
            {"feed": "recommended"}
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Machine Learning Applications"
        )

        self.assertNotContains(
            response,
            "Unrelated Research"
        )

    # =====================================
    # TEST 16: RECOMMENDATION RANKING
    # =====================================

    def test_recommended_feed_ranks_active_posts_higher(self):

        topic = Topic.objects.create(
            name="Data Science"
        )

        profile, created = Profile.objects.get_or_create(
            user=self.student_b
        )

        profile.topics.add(topic)

        popular_post = DiscussionPost.objects.create(
            author=self.staff,
            title="Popular Data Science Research",
            content="Research with community engagement."
        )

        popular_post.tags.add(topic)

        less_popular_post = DiscussionPost.objects.create(
            author=self.student_a,
            title="New Data Science Research",
            content="Another research post."
        )

        less_popular_post.tags.add(topic)

        # Add community activity to the popular post
        PostVote.objects.create(
            post=popular_post,
            user=self.student_a
        )

        self.client.force_login(self.student_b)

        response = self.client.get(
            reverse("discussions:post_list"),
            {"feed": "recommended"}
        )

        self.assertEqual(response.status_code, 200)

        recommended_ids = list(
            response.context["posts"].values_list(
                "id",
                flat=True
            )
        )

        self.assertLess(
            recommended_ids.index(popular_post.id),
            recommended_ids.index(less_popular_post.id)
        )

    # =====================================
    # TEST 17: EXCLUDE FOLLOWED POSTS FROM RECOMMENDATIONS
    # =====================================

    def test_recommended_feed_excludes_followed_sources(self):

        topic = Topic.objects.create(
            name="Cybersecurity"
        )

        followed_topic_post = DiscussionPost.objects.create(
            author=self.staff,
            title="Followed Cybersecurity Research",
            content="Cybersecurity research discussion."
        )

        followed_topic_post.tags.add(topic)

        MemberFollow.objects.create(
            follower=self.student_b,
            followed=self.student_a
        )

        TopicFollow.objects.create(
            user=self.student_b,
            topic=topic
        )

        self.client.force_login(self.student_b)

        response = self.client.get(
            reverse("discussions:post_list"),
            {"feed": "recommended"}
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            self.post.title
        )

        self.assertNotContains(
            response,
            "Followed Cybersecurity Research"
        )

    # =====================================
    # TEST 18: FOLLOW / UNFOLLOW TOPIC
    # =====================================

    def test_member_can_follow_and_unfollow_topic(self):

        topic = Topic.objects.create(
            name="Signal Processing"
        )

        topic_url = reverse(
            "accounts:toggle_topic_follow",
            args=[topic.id]
        )

        self.client.force_login(self.student_b)

        # First request: follow topic
        response = self.client.post(topic_url)

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            TopicFollow.objects.filter(
                user=self.student_b,
                topic=topic
            ).exists()
        )

        # Second request: unfollow topic
        response = self.client.post(topic_url)

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            TopicFollow.objects.filter(
                user=self.student_b,
                topic=topic
            ).exists()
        )

    # =====================================
    # TEST 19: CREATE POST WITH TAGS
    # =====================================

    def test_member_can_create_post_with_tags(self):

        topic = Topic.objects.create(
            name="Internet of Things"
        )

        self.client.force_login(self.student_a)

        response = self.client.post(
            reverse("discussions:post_create"),
            {
                "title": "IoT Research Project",
                "content": "Research about connected devices.",
                "tags": [str(topic.id)]
            }
        )

        self.assertEqual(response.status_code, 302)

        post = DiscussionPost.objects.get(
            title="IoT Research Project"
        )

        self.assertTrue(
            post.tags.filter(id=topic.id).exists()
        )

    # =====================================
    # TEST 20: EDIT POST TAGS
    # =====================================

    def test_member_can_update_post_tags(self):

        old_topic = Topic.objects.create(
            name="Artificial Intelligence"
        )

        new_topic = Topic.objects.create(
            name="Renewable Energy"
        )

        self.post.tags.add(old_topic)

        self.client.force_login(self.student_a)

        response = self.client.post(
            reverse(
                "discussions:post_edit",
                args=[self.post.id]
            ),
            {
                "title": self.post.title,
                "content": self.post.content,
                "tags": [str(new_topic.id)]
            }
        )

        self.assertEqual(response.status_code, 302)

        self.post.refresh_from_db()

        self.assertTrue(
            self.post.tags.filter(id=new_topic.id).exists()
        )

        self.assertFalse(
            self.post.tags.filter(id=old_topic.id).exists()
        )


    # =====================================
    # TEST 21: CREATE POST WITH PDF AND LINK
    # =====================================

    def test_member_can_create_post_with_pdf_and_link_resources(self):

        pdf_resource = ResearchResource.objects.create(
            title="Machine Learning Research PDF",
            description="Sample research paper",
            resource_type="paper",
            file="research_library/papers/sample.pdf",
            uploaded_by=self.student_a
        )

        link_resource = ResearchResource.objects.create(
            title="Machine Learning Research Link",
            description="External research resource",
            resource_type="link",
            url="https://example.com/research/ml",
            uploaded_by=self.student_a
        )

        self.client.force_login(self.student_a)

        response = self.client.post(
            reverse("discussions:post_create"),
            {
                "title": "Research Post With Attachments",
                "content": "Research discussion with library resources.",
                "resources": [
                    str(pdf_resource.id),
                    str(link_resource.id),
                ]
            }
        )

        self.assertEqual(response.status_code, 302)

        post = DiscussionPost.objects.get(
            title="Research Post With Attachments"
        )

        attached_ids = set(
            post.resources.values_list("id", flat=True)
        )

        self.assertEqual(
            attached_ids,
            {pdf_resource.id, link_resource.id}
        )

    # =====================================
    # TEST 22: EDIT POST ATTACHMENTS
    # =====================================

    def test_member_can_update_post_attachments(self):

        old_resource = ResearchResource.objects.create(
            title="Old Research Link",
            resource_type="link",
            url="https://example.com/old",
            uploaded_by=self.student_a
        )

        new_resource = ResearchResource.objects.create(
            title="New Research Link",
            resource_type="link",
            url="https://example.com/new",
            uploaded_by=self.student_a
        )

        self.post.resources.add(old_resource)

        self.client.force_login(self.student_a)

        response = self.client.post(
            reverse(
                "discussions:post_edit",
                args=[self.post.id]
            ),
            {
                "title": self.post.title,
                "content": self.post.content,
                "resources": [str(new_resource.id)]
            }
        )

        self.assertEqual(response.status_code, 302)

        self.post.refresh_from_db()

        self.assertTrue(
            self.post.resources.filter(
                id=new_resource.id
            ).exists()
        )

        self.assertFalse(
            self.post.resources.filter(
                id=old_resource.id
            ).exists()
        )
