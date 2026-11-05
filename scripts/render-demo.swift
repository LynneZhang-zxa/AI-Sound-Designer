// Assemble genuine test-editor snapshots and rendered audio; not a screen recording.
import Foundation
import AVFoundation
import AppKit
import ImageIO
import CoreVideo

let folder=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
let width=1200,height=1080,fps=10
let stages=[("before","Before — original sound"),("proposal","Preview — proposed changes, original audio"),("applied","Apply — darker and shorter"),("undo","Undo — original sound restored")]
let silent=folder.appendingPathComponent("demo-silent.mp4")
try? FileManager.default.removeItem(at:silent)
let writer=try AVAssetWriter(outputURL:silent,fileType:.mp4)
let input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:width,AVVideoHeightKey:height])
let adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32ARGB,kCVPixelBufferWidthKey as String:width,kCVPixelBufferHeightKey as String:height])
writer.add(input)
guard writer.startWriting() else {throw writer.error!}
writer.startSession(atSourceTime:.zero)
for (index,stage) in stages.enumerated() {
    let url=folder.appendingPathComponent(stage.0+".png")
    guard let source=CGImageSourceCreateWithURL(url as CFURL,nil),let image=CGImageSourceCreateImageAtIndex(source,0,nil) else {fatalError("Missing frame")}
    var optional:CVPixelBuffer?
    CVPixelBufferCreate(kCFAllocatorDefault,width,height,kCVPixelFormatType_32ARGB,nil,&optional)
    let buffer=optional!;CVPixelBufferLockBaseAddress(buffer,[])
    let context=CGContext(data:CVPixelBufferGetBaseAddress(buffer),width:width,height:height,bitsPerComponent:8,bytesPerRow:CVPixelBufferGetBytesPerRow(buffer),space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipFirst.rawValue)!
    context.setFillColor(CGColor(red:0.045,green:0.055,blue:0.065,alpha:1));context.fill(CGRect(x:0,y:0,width:width,height:height))
    context.draw(image,in:CGRect(x:120,y:100,width:960,height:880))
    NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(cgContext:context,flipped:false)
    (stage.1 as NSString).draw(at:NSPoint(x:120,y:1015),withAttributes:[.font:NSFont.boldSystemFont(ofSize:25),.foregroundColor:NSColor.white])
    ("Offline staged demo: actual JUCE editor + renderer. Not a Logic screen recording." as NSString).draw(at:NSPoint(x:120,y:65),withAttributes:[.font:NSFont.systemFont(ofSize:15),.foregroundColor:NSColor.lightGray])
    ("Same MIDI 48 / velocity 0.8. Gain parameter held; raw levels can differ. Local rules, not live AI." as NSString).draw(at:NSPoint(x:120,y:40),withAttributes:[.font:NSFont.systemFont(ofSize:14),.foregroundColor:NSColor.lightGray])
    NSGraphicsContext.restoreGraphicsState();CVPixelBufferUnlockBaseAddress(buffer,[])
    for frame in 0..<(4*fps) {
        while !input.isReadyForMoreMediaData {Thread.sleep(forTimeInterval:0.002)}
        if !adaptor.append(buffer,withPresentationTime:CMTime(value:Int64(index*4*fps+frame),timescale:Int32(fps))) {throw writer.error!}
    }
}
input.markAsFinished();let done=DispatchSemaphore(value:0);writer.finishWriting{done.signal()};done.wait()
guard writer.status == .completed else {throw writer.error!}
let video=AVURLAsset(url:silent),audio=AVURLAsset(url:folder.appendingPathComponent("demo-audio.wav"))
let composition=AVMutableComposition()
let duration=CMTime(seconds:16,preferredTimescale:600)
let videoTrack=composition.addMutableTrack(withMediaType:.video,preferredTrackID:kCMPersistentTrackID_Invalid)!
try videoTrack.insertTimeRange(CMTimeRange(start:.zero,duration:duration),of:video.tracks(withMediaType:.video)[0],at:.zero)
let audioTrack=composition.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid)!
try audioTrack.insertTimeRange(CMTimeRange(start:.zero,duration:duration),of:audio.tracks(withMediaType:.audio)[0],at:.zero)
let output=folder.appendingPathComponent("resonanca-demo.mp4");try? FileManager.default.removeItem(at:output)
let export=AVAssetExportSession(asset:composition,presetName:AVAssetExportPresetHighestQuality)!
export.outputURL=output;export.outputFileType = .mp4
let finished=DispatchSemaphore(value:0);export.exportAsynchronously{finished.signal()};finished.wait()
guard export.status == .completed else {throw export.error!}
print(output.path)
