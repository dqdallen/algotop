"""Optional real official SDK integration; all HTTP uses in-memory MockTransport.

Run after installing requirements-llm.txt. No provider request or valid key used.
"""
import importlib.util
import json
import unittest
from unittest.mock import patch
from extract import Config, extract, make_client

@unittest.skipUnless(importlib.util.find_spec('openai'), 'optional official SDK not installed')
class RealSDKOfflineTests(unittest.TestCase):
    def test_real_sdk_serializes_and_parses_both_output_modes(self):
        import httpx2 as httpx
        from openai import OpenAI
        text='什么是梯度下降？'
        for mode in ['json_schema','json_object']:
            requests=[]
            def respond(request):
                requests.append(request)
                self.assertEqual(request.url.path,'/v1/chat/completions')
                payload=json.loads(request.content)
                self.assertEqual(payload['response_format']['type'],mode)
                self.assertEqual(payload['max_completion_tokens'],4096)
                return httpx.Response(200,json={'id':'offline-fixture','object':'chat.completion','created':0,'model':'offline-model','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps({'questions':[{'question':text,'disposition':'common','evidence':{'quote':text,'start':0,'end':len(text)}}]})}}]})
            with patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
                with OpenAI(api_key='offline-not-a-real-api-key',base_url='https://sdk-test.invalid/v1',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(respond))) as sdk:
                    result=extract({'text':text,'source_url':'https://example.com/article','input_kind':'user_supplied_text'},{},sdk,Config(model='offline-model',format=mode))
            self.assertEqual(len(requests),1)
            self.assertEqual(len(result['question_candidates']),1)
            self.assertFalse(result['published'])

    def test_real_client_configuration_ignores_ambient_base_url(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'offline-not-a-real-api-key','OPENAI_BASE_URL':'https://untrusted.invalid/v1'},clear=True),patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            with make_client(Config(model='offline-model')) as sdk:
                self.assertEqual(str(sdk.base_url),'https://api.openai.com/v1/')
                self.assertEqual(sdk.max_retries,0)

if __name__=='__main__':unittest.main()
