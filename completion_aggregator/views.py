"""
Completion_aggregator App progress bar view.
"""
from __future__ import absolute_import, unicode_literals

from xblockutils.resources import ResourceLoader

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView

from .api.v1.views import CompletionDetailView

loader = ResourceLoader(__name__)


class CompletionProgressBarView(LoginRequiredMixin, TemplateView):
    """
    View to display the progress bar of a student in a course.
    """

    # pylint: disable=arguments-differ
    @xframe_options_exempt
    def get(self, request, course_key, chapter_id=None):
        """
        Fetch progress and render the template.
        """
        completion_percentage = 0
        new_req = request.GET.copy()
        new_req['username'] = request.user.username
        if chapter_id is not None:
            new_req['requested_fields'] = "chapter"
        request.GET = new_req
        with transaction.atomic():
            completion_resp = CompletionDetailView.as_view()(request, course_key).data

        if completion_resp:
            results = completion_resp.get('results')
            user_completion_percentage = self._get_user_completion(chapter_id, results)

            if user_completion_percentage:
                completion_percentage = user_completion_percentage

        template = 'chapter_completion_progress_bar.html' if chapter_id is not None else 'completion_progress_bar.html'
        return render(request, template, {
            'completion_percentage': completion_percentage,
        })

    def _get_user_completion(self, chapter_id, results):
        """
        Return the user completion percentage, using the completion response.

        In case the user completion cannot be returned as a result of missing user completion, we return None,
        indicating its absence.
        """
        if not results:
            return None

        user_completion = next(filter(lambda r: r, results), None)

        # No completion returned, hence we cannot get the percentage either
        # Indicate no user completion by returning None
        if not user_completion:
            return None

        if chapter_id:
            chapters = user_completion['chapter']
            chapter = next(filter(lambda c: c['block_key'].split('@')[-1] == chapter_id, chapters), None)

        completion_kind = chapter if chapter_id else user_completion

        if not completion_kind:
            return None

        return round(float(completion_kind['completion']['percent']) * 100)
