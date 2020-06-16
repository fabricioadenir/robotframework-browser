import { chromium, firefox, webkit } from 'playwright';
import { IPlaywrightServer, PlaywrightService } from './generated/playwright_grpc_pb';
import {sendUnaryData, ServerUnaryCall, Server, ServerCredentials} from "grpc";
import {openBrowserRequest, Empty, Response} from "./generated/playwright_pb";


class PlaywrightServer implements IPlaywrightServer {
    private browser: any;
    async closeBrowser(call: ServerUnaryCall<Empty>, callback: sendUnaryData<Response>): Promise<void> {
        console.log("Closing browser")
        await this.browser.close();
        const response = new Response();
        response.setLog('Log message from closeBrowser here')
        callback(null, response);
    }

    async openBrowser(call: ServerUnaryCall<openBrowserRequest>, callback: sendUnaryData<Response>): Promise<void> {
        const browserType = call.request.getBrowser()
        const url = call.request.getUrl()
        console.log("Open browser: " + browserType)
        if (browserType === 'firefox') {
            this.browser = await firefox.launch({headless: true});    
        } else if (browserType === 'chrome') {
            this.browser = await chromium.launch({headless: true})
        } else {
            this.browser = await webkit.launch()
        }
        const context = await this.browser.newContext();
        const page = await context.newPage();
        console.log('Go to url' + url)
        await page.goto(url);
        const response = new Response()
        response.setLog('Log message from openBrowser here')
        callback(null, response);
    }
}

const server = new Server();
server.addService<IPlaywrightServer>(PlaywrightService, new PlaywrightServer());
const port = server.bind(`localhost:0`, ServerCredentials.createInsecure());
console.log(`Listening on ${port}`);
server.start();