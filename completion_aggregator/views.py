"""
completion_aggregator App progress bar view
"""
from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView
from xblockutils.resources import ResourceLoader

from .api.v1.views import CompletionDetailView

loader = ResourceLoader(__name__)


class CompletionProgressBarView(LoginRequiredMixin, TemplateView):
    """
    View to display the progress bar of a student in a course
    """
    @xframe_options_exempt
    def get(self, request, course_key, chapter_id=None):
        """
        Fetch progress and render the template.
        """
        username = request.user.username
        completion_percentage = 0
        if chapter_id is not None:
            new_req = request.GET.copy()
            new_req['requested_fields'] = "chapter"
            request.GET = new_req
        completion_resp = CompletionDetailView.as_view()(request, course_key).data
        if completion_resp:
            results = completion_resp.get('results')
            for user_completion_dict in results:
                if user_completion_dict.get('username') == username:
                    if chapter_id is not None:
                        chapters = user_completion_dict['chapter']
                        for chapter in chapters:
                            block_id = chapter['block_key'].split('@')[-1]
                            if block_id == chapter_id:
                                completion_percentage = float(chapter['completion']['percent']) * 100
                    else:
                        completion_percentage = float(user_completion_dict['completion']['percent']) * 100

        if chapter_id is not None:
            return render(request, 'chapter_completion_progress_bar.html', {
                'chapter_completion_percentage': completion_percentage,
            })
        else:
            return render(request, 'completion_progress_bar.html', {
                'completion_percentage': completion_percentage,
            })
