import os, sys
import requests

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader
from django.views.decorators.csrf import csrf_protect

sys.path.append(os.path.join(os.path.dirname(__file__), "..",
                             "tellina_learning_module"))
from bashlex import data_tools

from website.models import NLRequest, Translation, NLRequestIPAddress, Vote

WEBSITE_DEVELOP = False
CACHE_TRANSLATIONS = True

from website.cmd2html import tokens2html
from . import functions

def ip_address_required(f):
    @functions.wraps(f)
    def g(request, *args, **kwargs):
        ip_address = request.COOKIES['ip_address']
        if not ip_address:
            # use empty IP address if cookie reading fails
            ip_address = ''
        return f(request, *args, ip_address=ip_address, **kwargs)
    return g

if not WEBSITE_DEVELOP:
    from website.helper_interface import translate_fun

def info(request):
    template = loader.get_template('translator/info.html')
    context = {}
    return HttpResponse(template.render(context, request))

@csrf_protect
@ip_address_required
def translate(request, ip_address):
    template = loader.get_template('translator/translate.html')
    if request.method == 'POST':
        request_str = request.POST.get('request_str')
    else:
        request_str = request.GET.get('request_str')

    if not request_str or not request_str.strip():
        return redirect('/')
    
    while request_str.endswith('/'):
        request_str = request_str[:-1]

    trans_list = []
    html_strs = []
    if CACHE_TRANSLATIONS and NLRequest.objects.filter(
            request_str=request_str).exists():
        # if the natural language request string has been translated before,
        # directly output previously cached translations
        if Translation.objects.filter(
                request__request_str=request_str).exists():
            # model translations exist
            cached_trans = Translation.objects.filter(
                request__request_str=request_str)
            for trans in cached_trans:
                print(trans.pred_cmd)
                pred_tree = data_tools.bash_parser(trans.pred_cmd)
                if pred_tree is not None:
                    trans_list.append(trans)
                    html_str = tokens2html(pred_tree)
                    html_strs.append(html_str)
    # check if the natural language request has been issued by the IP
    # address before
    try:
        nl_request = NLRequest.objects.get(request_str=request_str)
    except ObjectDoesNotExist:
        nl_request = NLRequest.objects.create(request_str=request_str)

    # save the natural language request issued by this IP Address
    if not NLRequestIPAddress.objects.filter(
            request__request_str=request_str, ip_address=ip_address).exists():
        NLRequestIPAddress.objects.create(
            request=nl_request, ip_address=ip_address)

    if not trans_list:
        if not WEBSITE_DEVELOP:
            # call learning model and store the translations
            batch_outputs, output_logits = translate_fun(request_str)

            if batch_outputs:
                top_k_predictions = batch_outputs[0]
                top_k_scores = output_logits[0]

                for i in range(len(top_k_predictions)):
                    pred_tree, pred_cmd, outputs = top_k_predictions[i]
                    score = top_k_scores[i]

                    trans = Translation.objects.create(
                        request=nl_request, pred_cmd=pred_cmd, score=score)

                    trans_list.append(trans)
                    html_str = tokens2html(pred_tree)
                    html_strs.append(html_str)

    translation_list = []
    for trans, html_str in zip(trans_list, html_strs):
        upvoted, downvoted, starred = "", "", ""
        if Vote.objects.filter(translation=trans, ip_address=ip_address)\
            .exists():
            v = Vote.objects.get(translation=trans, ip_address=ip_address)
            upvoted = 1 if v.upvoted else ""
            downvoted = 1 if v.downvoted else ""
            starred = 1 if v.starred else ""
        translation_list.append((trans, upvoted, downvoted, starred,
                             trans.pred_cmd.replace('\\', '\\\\'), html_str))

    # sort translation_list based on voting results
    translation_list.sort(key=lambda x: x[0].num_votes + x[0].score,
                          reverse=True)
    context = {
        'nl_request': nl_request,
        'trans_list': translation_list
    }
    return HttpResponse(template.render(context, request))

@ip_address_required
def vote(request, ip_address):
    id = request.GET['id']
    upvoted = request.GET['upvoted']
    downvoted = request.GET['downvoted']
    starred = request.GET['starred']

    translation = Translation.objects.get(id=id)

    # store voting record in the DB
    if Vote.objects.filter(translation=translation, ip_address=ip_address)\
        .exists():
        vote = Vote.objects.get(translation=translation, ip_address=ip_address)
        if upvoted == 'true' and not vote.upvoted:
            translation.num_upvotes += 1
        if downvoted == 'true' and not vote.downvoted:
            translation.num_downvotes += 1
        if starred == 'true' and not vote.starred:
            translation.num_stars += 1
        if upvoted == 'false' and vote.upvoted:
            translation.num_upvotes -= 1
        if downvoted == 'false' and vote.downvoted:
            translation.num_downvotes -= 1
        if starred == 'false' and vote.starred:
            translation.num_stars -= 1
        vote.upvoted = (upvoted == 'true')
        vote.downvoted = (downvoted == 'true')
        vote.starred = (starred == 'true')
        vote.save()
    else:
        Vote.objects.create(
            translation=translation, ip_address=ip_address,
            upvoted=(upvoted == 'true'),
            downvoted=(downvoted == 'true'),
            starred=(starred == 'true')
        )
        if upvoted == 'true':
            translation.num_upvotes += 1
        if downvoted == 'true':
            translation.num_downvotes += 1
        if starred == 'true':
            translation.num_stars += 1
    translation.save()

    return HttpResponse()

def remember_ip_address(request):
    ip_address = request.GET['ip_address']
    resp = HttpResponse()
    resp.set_cookie('ip_address', ip_address)
    return resp

def recently_asked(request):
    latest_request_list = NLRequestIPAddress.objects.order_by(
        '-request__submission_time')
    template = loader.get_template('analyzer/recently_asked.html')

    # Display user's physical location in front end instead of exposing their
    # IP addresses
    latest_request_with_locations = []
    for request_ip_address in latest_request_list:
        ip_address = request_ip_address.ip_address
        r = requests.get('http://ipinfo.io/{}/json'.format(ip_address))
        org = r.json()['org']
        city = r.json()['city']
        region = r.json()['region']
        country = r.json()['country']
        latest_request_with_locations.append((request_ip_address.request,
                                              org, city, region, country))
    context = {
        'latest_request_list': latest_request_with_locations
    }
    return HttpResponse(template.render(context, request))

def index(request):
    example_request_list = [
        'remove all pdfs in my current directory',
        'delete all *.txt files in "myDir/"',
        'list files in "myDir/" that have been modified within 24 hours',
        'find all files named "test*.cpp" and move them to "project/code/"',
        'find all files larger than a gigabyte in the current folder',
        'find all png files larger than 50M that were last modified more than 30 days ago'
    ]
    latest_request_list = NLRequest.objects.order_by('-submission_time')[:6]
    template = loader.get_template('translator/index.html')
    context = {
        'example_request_list': example_request_list,
        'latest_request_list': latest_request_list
    }
    return HttpResponse(template.render(context, request))
