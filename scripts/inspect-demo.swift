import Foundation
import AVFoundation
import ImageIO
import UniformTypeIdentifiers
let folder=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
let asset=AVURLAsset(url:folder.appendingPathComponent("resonanca-demo.mp4"))
let videos=asset.tracks(withMediaType:.video),audios=asset.tracks(withMediaType:.audio)
guard videos.count==1 && audios.count==1 && abs(asset.duration.seconds-16) < 0.15 else {fatalError("Invalid demo duration/tracks")}
let image=try AVAssetImageGenerator(asset:asset).copyCGImage(at:CMTime(seconds:1,preferredTimescale:600),actualTime:nil)
let target=folder.appendingPathComponent("poster.png")
let dest=CGImageDestinationCreateWithURL(target as CFURL,UTType.png.identifier as CFString,1,nil)!
CGImageDestinationAddImage(dest,image,nil);guard CGImageDestinationFinalize(dest) else{fatalError("Cannot export poster")}
let data:[String:Any]=["duration_seconds":asset.duration.seconds,"video_tracks":videos.count,"audio_tracks":audios.count,"width":videos[0].naturalSize.width,"height":videos[0].naturalSize.height]
let json=try JSONSerialization.data(withJSONObject:data,options:[.prettyPrinted,.sortedKeys]);try json.write(to:folder.appendingPathComponent("video-verification.json"));print(String(data:json,encoding:.utf8)!)
